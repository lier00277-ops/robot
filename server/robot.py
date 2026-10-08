# -*- coding: utf-8 -*-
"""
虚拟机器人设备模型（设备层 / 数字孪生）

本模块只负责"设备本身"，与 HTTP 通信完全解耦：
  * 设备状态机：offline / idle / moving / executing_task / stopped
  * 运动模拟：asyncio 后台任务按真实时间演化坐标（10Hz）
  * 预设任务：forward / square / circle / triangle / patrol
  * 传感器模拟：基准值 + 随机扰动，并与设备状态物理联动
  * 状态持久化：变更节流写入 device_state.json，服务重启可恢复

设计说明：真实 IoT 场景中这一层就是"设备影子（Device Shadow）"，
当前阶段用 HTTP 通信，将来替换为 MQTT/CoAP 时无需改动本层。
"""

import asyncio
import json
import math
import os
import random
import time

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_state.json")

UPDATE_INTERVAL = 0.1        # 运动模拟刷新周期（秒），即 10Hz
PERSIST_INTERVAL = 0.5       # 状态落盘节流（秒）
HEARTBEAT_TIMEOUT = 30.0     # 收到心跳后超过该秒数未再收到则判定离线
TASK_SPEED = 0.6             # 预设任务默认速度（m/s）
TURN_SPEED = 180.0           # 转向角速度（度/秒）
LEG_LENGTH = 0.5             # forward / square / triangle 单边长度（m）

PRESET_TASKS = ("forward", "square", "circle", "triangle", "patrol")


class BusyError(Exception):
    """设备正忙（运动中或任务执行中），拒绝新指令。"""


class VirtualRobot:
    """虚拟机器人设备（全局单例）。"""

    def __init__(self, device_id="robot-001", state_file=STATE_FILE):
        self.device_id = device_id
        self.state_file = state_file

        # ---- 核心状态 ----
        self.online = False
        self.run_state = "offline"      # offline / idle / moving / executing_task / stopped
        self.current_task = None        # 正在执行的预设任务名
        self.current_move = None        # 正在执行的 move 参数
        self.position = {"x": 0.0, "y": 0.0}    # 坐标（米）
        self.heading = 0.0              # 朝向角（度，逆时针为正）
        self.speed = 0.0                # 当前速度（m/s）
        self.turn_rate = 0.0            # 当前角速度（度/秒，用于 IMU 联动）
        self.battery = 100.0            # 电量（%）

        # ---- 运行时 ----
        self.started_at = time.time()
        self.last_heartbeat = None
        self._motion_task = None        # 当前运动/任务 asyncio.Task
        self._last_persist = 0.0
        self._restore()                 # 启动时恢复上次保存的状态

    # ==================== 生命周期 ====================

    def power_on(self):
        """设备上电：offline -> online/idle。"""
        self.online = True
        self.run_state = "idle"
        self.speed = 0.0
        self.turn_rate = 0.0
        self.current_task = None
        self.current_move = None
        self.last_heartbeat = None      # 上电后未收到客户端心跳前，不启动超时计时
        self._persist(force=True)

    def shutdown(self):
        """服务关闭：保存最终状态。"""
        self.online = False
        self.run_state = "offline"
        self._persist(force=True)

    def heartbeat(self):
        """接收客户端心跳，刷新在线判定。"""
        self.online = True
        self.last_heartbeat = time.time()
        self._persist(force=True)

    @property
    def alive(self):
        """在线判定：收到过心跳后，超过 HEARTBEAT_TIMEOUT 未再收到则离线。"""
        if not self.online:
            return False
        if self.last_heartbeat is None:
            return True
        return (time.time() - self.last_heartbeat) < HEARTBEAT_TIMEOUT

    @property
    def busy(self):
        """设备是否正忙（有未结束的运动/任务）。"""
        return self._motion_task is not None and not self._motion_task.done()

    # ==================== 查询 ====================

    def status(self):
        """设备状态快照（GET /status 的返回体）。"""
        return {
            "device_id": self.device_id,
            "online": self.alive,
            "run_state": self.run_state,
            "current_task": self.current_task,
            "position": {k: round(v, 2) for k, v in self.position.items()},
            "heading": round(self.heading, 1),
            "speed": round(self.speed, 2),
            "battery": round(self.battery, 1),
            "uptime_sec": round(time.time() - self.started_at, 1),
        }

    def sensors(self):
        """传感器读数：基准值 + 随机扰动，且与运动状态物理联动。"""
        moving = self.run_state in ("moving", "executing_task")
        return {
            "temperature_c": round(32.0 + (8.0 if moving else 0.0) + random.uniform(-0.8, 0.8), 2),
            "humidity_pct": round(50.0 + random.uniform(-5.0, 5.0), 2),
            "battery_voltage_v": round(12.6 * self.battery / 100.0 + random.uniform(-0.05, 0.05), 2),
            "obstacle_distance_cm": round(
                random.uniform(8.0, 120.0) if moving else random.uniform(8.0, 300.0), 1),
            "imu": {
                "ax": round(random.uniform(-0.02, 0.02), 3),
                "ay": round(random.uniform(-0.02, 0.02), 3),
                "az": round(9.81 + random.uniform(-0.02, 0.02), 3),
                "gyro_z_deg_s": round(self.turn_rate + random.uniform(-1.0, 1.0), 2),
            },
            "wheel_speed_rpm": round(
                abs(self.speed) * 60.0 / (2.0 * math.pi * 0.05) + random.uniform(-2.0, 2.0), 1),
        }

    # ==================== 指令入口 ====================

    def start_move(self, direction, speed, distance):
        """下发单步运动指令（POST /move）。"""
        if self.busy:
            raise BusyError("设备正忙（%s），请先调用 /stop" % (self.current_task or "运动中"))
        self._motion_task = asyncio.create_task(self._move(direction, speed, distance))

    def start_task(self, name):
        """启动预设任务（POST /task）。"""
        if name not in PRESET_TASKS:
            raise ValueError("未知预设任务: %s，可选 %s" % (name, "/".join(PRESET_TASKS)))
        if self.busy:
            raise BusyError("设备正忙（%s），请先调用 /stop" % (self.current_task or "运动中"))
        self._motion_task = asyncio.create_task(self._execute_task(name))

    def stop(self):
        """停止设备：中断正在进行的运动/任务（POST /stop）。"""
        if self.busy:
            self._motion_task.cancel()
        self.run_state = "stopped"
        self.speed = 0.0
        self.turn_rate = 0.0
        self.current_task = None
        self.current_move = None
        self._persist(force=True)

    # ==================== 运动模拟（后台任务） ====================

    async def _move(self, direction, speed, distance):
        """单步运动：left/right 先原地转 90 度再前进，backward 直接后退。"""
        self.run_state = "moving"
        self.current_move = {"direction": direction, "speed": speed, "distance": distance}
        self._persist(force=True)
        try:
            # 约定：面朝 +x（东）时，左转朝 +y（北）= 逆时针 +90°
            if direction == "left":
                await self._turn(90.0)
            elif direction == "right":
                await self._turn(-90.0)
            sign = -1.0 if direction == "backward" else 1.0
            done = 0.0
            while done < distance:
                dt = min(UPDATE_INTERVAL, (distance - done) / speed)
                step = speed * sign * dt
                rad = math.radians(self.heading)
                self.position["x"] += step * math.cos(rad)
                self.position["y"] += step * math.sin(rad)
                self.speed = speed
                self.battery = max(0.0, self.battery - 0.5 * dt)
                done += speed * dt
                self._persist()
                await asyncio.sleep(dt)
        except asyncio.CancelledError:
            self.run_state = "stopped"
            raise
        finally:
            # 仅当本任务仍是当前任务时清理状态，避免影响新任务
            if self._motion_task is asyncio.current_task():
                self.speed = 0.0
                self.current_move = None
                if self.run_state != "stopped":
                    self.run_state = "idle"
                self._persist(force=True)

    async def _run_leg(self, distance, speed=TASK_SPEED):
        """沿当前朝向直行一段距离（任务执行器的基础动作）。"""
        done = 0.0
        while done < distance:
            dt = min(UPDATE_INTERVAL, (distance - done) / speed)
            step = speed * dt
            rad = math.radians(self.heading)
            self.position["x"] += step * math.cos(rad)
            self.position["y"] += step * math.sin(rad)
            self.speed = speed
            self.battery = max(0.0, self.battery - 0.5 * dt)
            done += speed * dt
            self._persist()
            await asyncio.sleep(dt)
        self.speed = 0.0

    async def _turn(self, delta_deg, turn_speed=TURN_SPEED):
        """原地转向 delta_deg 度。"""
        remaining = delta_deg
        self.turn_rate = turn_speed if delta_deg > 0 else -turn_speed
        while abs(remaining) > 0.5:
            step = self.turn_rate * UPDATE_INTERVAL
            if abs(step) > abs(remaining):
                step = remaining
            self.heading = (self.heading + step) % 360.0
            remaining -= step
            self.battery = max(0.0, self.battery - 0.2 * UPDATE_INTERVAL)
            self._persist()
            await asyncio.sleep(UPDATE_INTERVAL)
        self.heading = round(self.heading, 2) % 360.0
        self.turn_rate = 0.0

    async def _execute_task(self, name):
        """预设任务执行器：路径规划 -> 逐段执行 -> 自动回 idle。"""
        self.run_state = "executing_task"
        self.current_task = name
        self._persist(force=True)
        try:
            if name == "forward":
                await self._run_leg(LEG_LENGTH)
            elif name == "square":
                for _ in range(4):
                    await self._run_leg(LEG_LENGTH)
                    await self._turn(90.0)
            elif name == "circle":
                step_len = 2.0 * math.pi * 0.5 / 36.0      # 半径 0.5m 的圆
                for _ in range(36):
                    await self._run_leg(step_len)
                    await self._turn(10.0)
            elif name == "triangle":
                for _ in range(3):
                    await self._run_leg(LEG_LENGTH)
                    await self._turn(120.0)
            elif name == "patrol":
                while True:                               # 持续巡逻，直到 /stop
                    await self._run_leg(0.8)
                    await self._turn(90.0)
        except asyncio.CancelledError:
            self.run_state = "stopped"
            raise
        finally:
            if self._motion_task is asyncio.current_task():
                self.speed = 0.0
                self.turn_rate = 0.0
                self.current_task = None
                if self.run_state != "stopped":
                    self.run_state = "idle"
                self._persist(force=True)

    # ==================== 持久化 ====================

    def _snapshot(self):
        """要保存到 JSON 的状态字段。"""
        return {
            "device_id": self.device_id,
            "online": self.online,
            "run_state": self.run_state,
            "current_task": self.current_task,
            "position": self.position,
            "heading": self.heading,
            "battery": self.battery,
            "last_heartbeat": self.last_heartbeat,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _persist(self, force=False):
        """状态落盘：运动中节流（每 0.5s 一次），状态切换时强制写入。"""
        now = time.time()
        if not force and now - self._last_persist < PERSIST_INTERVAL:
            return
        self._last_persist = now
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._snapshot(), f, ensure_ascii=False, indent=2)
        except OSError:
            pass    # 落盘失败不影响服务运行

    def _restore(self):
        """启动时从 device_state.json 恢复状态。"""
        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        self.online = bool(data.get("online", False))
        self.run_state = data.get("run_state", "offline")
        pos = data.get("position") or {}
        self.position = {"x": float(pos.get("x", 0.0)), "y": float(pos.get("y", 0.0))}
        self.heading = float(data.get("heading", 0.0))
        self.battery = float(data.get("battery", 100.0))
