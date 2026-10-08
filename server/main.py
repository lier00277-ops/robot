# -*- coding: utf-8 -*-
"""
虚拟机器人设备服务 —— FastAPI 通信层
（灵境竞赛组-物联网方向-第一阶段考核）

Ubuntu 启动方式:
    uvicorn main:app --host 0.0.0.0 --port 8000
    或直接运行 run.sh

接口一览:
    GET  /            服务信息
    GET  /status      设备在线状态、运行状态
    GET  /sensor      模拟传感器数据
    POST /move        运动控制 {direction, speed, distance}
    POST /stop        停止设备
    POST /task        预设任务 {task}
    POST /heartbeat   心跳上报（附加加分接口）

设计说明：本文件只是"通信层"，设备状态与运动模拟在 robot.py 中，
两层解耦，将来可把 HTTP 替换为 MQTT/CoAP 而不改设备层。
"""

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from robot import PRESET_TASKS, BusyError, VirtualRobot

app = FastAPI(
    title="虚拟机器人设备服务",
    description="灵境竞赛组-物联网方向-第一阶段考核：设备状态查询与控制",
    version="1.0.0",
)

robot = VirtualRobot()      # 全局唯一设备实例：状态保存在这里并持续更新


class MoveRequest(BaseModel):
    """POST /move 运动控制参数。"""
    direction: Literal["forward", "backward", "left", "right"] = "forward"
    speed: float = Field(default=0.5, gt=0.0, le=2.0, description="速度（m/s）")
    distance: float = Field(default=0.5, gt=0.0, le=5.0, description="距离（m）")


class TaskRequest(BaseModel):
    """POST /task 预设任务参数。"""
    task: Literal["forward", "square", "circle", "triangle", "patrol"]


@app.on_event("startup")
def _startup():
    robot.power_on()


@app.on_event("shutdown")
def _shutdown():
    robot.shutdown()


@app.get("/", summary="服务信息")
def root():
    return {
        "service": "虚拟机器人设备服务",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": ["/status", "/sensor", "/move", "/stop", "/task", "/heartbeat"],
    }


@app.get("/status", summary="查询设备在线状态与运行状态")
def get_status():
    return robot.status()


@app.get("/sensor", summary="查询模拟传感器数据")
def get_sensor():
    return robot.sensors()


@app.post("/move", summary="运动控制")
async def move(req: MoveRequest):
    try:
        robot.start_move(req.direction, req.speed, req.distance)
    except BusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "message": "运动指令已下发，设备开始移动",
        "move": {"direction": req.direction, "speed": req.speed, "distance": req.distance},
        "status": robot.status(),
    }


@app.post("/stop", summary="停止设备")
async def stop():
    robot.stop()
    return {"message": "设备已停止", "status": robot.status()}


@app.post("/task", summary="执行预设任务")
async def task(req: TaskRequest):
    try:
        robot.start_task(req.task)
    except BusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"message": "预设任务已启动", "task": req.task, "status": robot.status()}


@app.post("/heartbeat", summary="心跳上报（附加接口）")
def heartbeat():
    robot.heartbeat()
    return {"message": "心跳已更新", "status": robot.status()}
