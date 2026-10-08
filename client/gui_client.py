# -*- coding: utf-8 -*-
"""
Windows Tkinter 图形客户端（带机器人轨迹可视化）
（灵境竞赛组-物联网方向-第一阶段考核）

用法:
    python gui_client.py                       # 默认连接 127.0.0.1:8000
    python gui_client.py --host 192.168.1.10   # 连接虚拟机
    python gui_client.py --selftest            # 自检模式：构建界面后立即退出
"""
import argparse
import json
import math
import time
import tkinter as tk
from tkinter import messagebox, ttk

import requests

SCALE = 90.0            # 画布比例：像素/米
CANVAS = 460            # 画布边长（像素）
GRID_RANGE = 2          # 网格范围 -2 ~ 2 米
POLL_MS = 400           # /status 轮询周期（毫秒）

STATE_COLOR = {
    "idle": "#2b2",
    "moving": "#f80",
    "executing_task": "#08f",
    "stopped": "#e33",
    "offline": "#888",
}


class RobotGUI:
    def __init__(self, root, host, port):
        self.root = root
        self.base = "http://%s:%d" % (host, port)
        self.history = []           # 轨迹点 [(x, y), ...]
        self.last_pos = None
        self.last_status = {}
        self.conn_err_shown = False

        root.title("虚拟机器人控制台 - Windows 客户端")
        root.geometry("940x680")
        self._build()
        self.poll_status()

    # ---------------- 界面 ----------------
    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="服务器:").pack(side="left")
        self.host_var = tk.StringVar(value=self.base.split("//")[1].split(":")[0])
        ttk.Entry(top, textvariable=self.host_var, width=16).pack(side="left", padx=(4, 2))
        self.port_var = tk.StringVar(value=self.base.rsplit(":", 1)[1])
        ttk.Entry(top, textvariable=self.port_var, width=6).pack(side="left")
        ttk.Button(top, text="应用", command=self.apply_server).pack(side="left", padx=6)
        ttk.Button(top, text="连接测试", command=self.test_conn).pack(side="left")
        self.state_var = tk.StringVar(value="未连接")
        ttk.Label(top, textvariable=self.state_var, foreground="#d33").pack(side="left", padx=12)

        body = ttk.Frame(self.root, padding=8)
        body.pack(fill="both", expand=True)

        # ---- 左侧控制区 ----
        left = ttk.LabelFrame(body, text=" 控制区 ", padding=8)
        left.pack(side="left", fill="y")

        ttk.Button(left, text="查询设备状态 (GET /status)",
                   command=self.on_status).pack(fill="x", pady=3)
        ttk.Button(left, text="查询传感器 (GET /sensor)",
                   command=self.on_sensor).pack(fill="x", pady=3)

        mv = ttk.LabelFrame(left, text=" 运动控制 /move ", padding=6)
        mv.pack(fill="x", pady=6)
        ttk.Label(mv, text="方向:").grid(row=0, column=0, sticky="w")
        self.dir_var = tk.StringVar(value="forward")
        ttk.Combobox(mv, textvariable=self.dir_var, width=10, state="readonly",
                     values=("forward", "backward", "left", "right")).grid(row=0, column=1, pady=2)
        ttk.Label(mv, text="速度 m/s:").grid(row=1, column=0, sticky="w")
        self.speed_var = tk.StringVar(value="0.5")
        ttk.Entry(mv, textvariable=self.speed_var, width=10).grid(row=1, column=1, pady=2)
        ttk.Label(mv, text="距离 m:").grid(row=2, column=0, sticky="w")
        self.dist_var = tk.StringVar(value="0.5")
        ttk.Entry(mv, textvariable=self.dist_var, width=10).grid(row=2, column=1, pady=2)
        ttk.Button(mv, text="发送移动指令", command=self.on_move).grid(
            row=3, column=0, columnspan=2, pady=(4, 0), sticky="ew")

        tkf = ttk.LabelFrame(left, text=" 预设任务 /task ", padding=6)
        tkf.pack(fill="x", pady=6)
        self.task_var = tk.StringVar(value="square")
        ttk.Combobox(tkf, textvariable=self.task_var, width=14, state="readonly",
                     values=("forward", "square", "circle", "triangle", "patrol")).pack(pady=2)
        ttk.Button(tkf, text="执行预设任务", command=self.on_task).pack(fill="x", pady=(4, 0))

        ttk.Button(left, text="停止设备 (POST /stop)",
                   command=self.on_stop).pack(fill="x", pady=3)
        ttk.Button(left, text="心跳上报 (POST /heartbeat)",
                   command=self.on_heartbeat).pack(fill="x", pady=3)

        # ---- 右侧轨迹画布 ----
        right = ttk.LabelFrame(body, text=" 机器人轨迹（镜头跟随，1 格 = 1 米） ", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.canvas = tk.Canvas(right, width=CANVAS, height=CANVAS, bg="white")
        self.canvas.pack()

        # ---- 底部日志 ----
        logf = ttk.LabelFrame(self.root, text=" 请求 / 响应日志 ", padding=6)
        logf.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log_text = tk.Text(logf, height=8, state="disabled", wrap="none")
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)

    def apply_server(self):
        self.base = "http://%s:%s" % (self.host_var.get().strip(), self.port_var.get().strip())
        self.history.clear()
        self.last_pos = None
        self.conn_err_shown = False
        self.draw()
        self.log("服务器地址切换为 %s" % self.base)

    def test_conn(self):
        code, data = self.request("GET", "/status")
        if code and 200 <= code < 300:
            self.state_var.set("已连接: %s" % (data or {}).get("run_state", "?"))
            messagebox.showinfo("连接测试", "连接成功！")
        else:
            self.state_var.set("未连接")
            messagebox.showerror("连接测试", "连接失败，请检查服务器是否启动、IP/端口是否正确。")

    # ---------------- 网络 ----------------
    def request(self, method, path, payload=None):
        self.log(">>> %s %s %s" % (
            method, path, json.dumps(payload, ensure_ascii=False) if payload else ""))
        try:
            resp = requests.request(method, self.base + path, json=payload, timeout=5)
        except requests.exceptions.ConnectionError:
            self.log("<<< 连接失败: %s （服务器未启动 / IP 错误 / 防火墙拦截）" % self.base)
            return None, None
        except requests.exceptions.Timeout:
            self.log("<<< 请求超时: %s" % path)
            return None, None
        try:
            data = resp.json()
        except ValueError:
            data = None
        self.log("<<< HTTP %s %s" % (resp.status_code, json.dumps(data, ensure_ascii=False, indent=2)))
        return resp.status_code, data

    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", "[%s] %s\n" % (time.strftime("%H:%M:%S"), text))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ---------------- 按钮回调 ----------------
    def on_status(self):
        code, data = self.request("GET", "/status")
        if code and 200 <= code < 300:
            self.state_var.set("在线 | 状态: %s | 位置: (%.2f, %.2f) | 电量: %.0f%%" % (
                data["run_state"], data["position"]["x"], data["position"]["y"],
                data.get("battery", 0)))

    def on_sensor(self):
        self.request("GET", "/sensor")

    def on_move(self):
        try:
            speed = float(self.speed_var.get())
            distance = float(self.dist_var.get())
        except ValueError:
            messagebox.showerror("参数错误", "速度和距离必须是数字")
            return
        code, data = self.request("POST", "/move", {
            "direction": self.dir_var.get(), "speed": speed, "distance": distance})
        if code and code >= 400:
            messagebox.showwarning("服务器拒绝", "HTTP %s: %s" % (
                code, (data or {}).get("detail", "")))

    def on_task(self):
        code, data = self.request("POST", "/task", {"task": self.task_var.get()})
        if code and code >= 400:
            messagebox.showwarning("服务器拒绝", "HTTP %s: %s" % (
                code, (data or {}).get("detail", "")))

    def on_stop(self):
        self.request("POST", "/stop")

    def on_heartbeat(self):
        self.request("POST", "/heartbeat")

    # ---------------- 轮询与绘制 ----------------
    def poll_status(self):
        try:
            resp = requests.get(self.base + "/status", timeout=1.5)
            data = resp.json()
            self.last_status = data
            self.conn_err_shown = False
            x, y = data["position"]["x"], data["position"]["y"]
            self.state_var.set("在线 | 状态: %s | 位置: (%.2f, %.2f) | 电量: %.0f%%" % (
                data["run_state"], x, y, data.get("battery", 0)))
            if self.last_pos != (x, y):
                self.history.append((x, y))
                if len(self.history) > 2000:      # 轨迹历史上限，防止长期巡逻导致绘制变慢
                    self.history = self.history[-2000:]
                self.last_pos = (x, y)
                self.draw()
        except (requests.exceptions.RequestException, ValueError, KeyError):
            if not self.conn_err_shown:
                self.state_var.set("未连接（服务不可达）")
                self.conn_err_shown = True
        self.root.after(POLL_MS, self.poll_status)

    def draw(self):
        """绘制网格、轨迹与机器人（镜头跟随：机器人始终居中，跑多远都不出画布）。"""
        c = self.canvas
        c.delete("all")
        cx = cy = CANVAS / 2

        # 镜头跟随：以机器人当前位置为画布中心
        cam_x, cam_y = (0.0, 0.0)
        if self.history:
            cam_x, cam_y = self.history[-1]

        # 网格与坐标轴（随镜头平移，1 格 = 1 米）
        gx0, gx1 = math.floor(cam_x - GRID_RANGE), math.ceil(cam_x + GRID_RANGE)
        gy0, gy1 = math.floor(cam_y - GRID_RANGE), math.ceil(cam_y + GRID_RANGE)
        for gx in range(gx0, gx1 + 1):
            px = cx + (gx - cam_x) * SCALE
            c.create_line(px, 0, px, CANVAS, fill="#d00" if gx == 0 else "#ddd")
            if gx != 0:
                c.create_text(px + 3, cy + 10, text="%dm" % gx, fill="#999", anchor="nw")
        for gy in range(gy0, gy1 + 1):
            py = cy - (gy - cam_y) * SCALE
            c.create_line(0, py, CANVAS, py, fill="#d00" if gy == 0 else "#ddd")
            if gy != 0:
                c.create_text(cx + 8, py - 8, text="%dm" % gy, fill="#999", anchor="nw")

        # 原点 (0,0) 十字标记（在视野内时显示）
        ox, oy = cx - cam_x * SCALE, cy + cam_y * SCALE
        if 0 <= ox <= CANVAS and 0 <= oy <= CANVAS:
            c.create_line(ox - 6, oy, ox + 6, oy, fill="#d00", width=2)
            c.create_line(ox, oy - 6, ox, oy + 6, fill="#d00", width=2)
            c.create_text(ox + 8, oy + 8, text="原点", fill="#d00", anchor="nw")

        # 轨迹（历史点换算到镜头坐标系）
        if len(self.history) >= 2:
            pts = []
            for x, y in self.history:
                pts.extend([cx + (x - cam_x) * SCALE, cy - (y - cam_y) * SCALE])
            c.create_line(*pts, fill="#07c", width=2, smooth=True)

        # 机器人（始终画在中心）
        if self.history:
            x, y = self.history[-1]
            color = STATE_COLOR.get(self.last_status.get("run_state", "offline"), "#2b2")
            c.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill=color, outline="#333")
            rad = math.radians(self.last_status.get("heading", 0.0))
            c.create_line(cx, cy, cx + 16 * math.cos(rad), cy - 16 * math.sin(rad),
                          fill="#333", width=2, arrow="last")
            c.create_text(cx + 12, cy - 12, text="(%.2f, %.2f)" % (x, y),
                          fill="#333", anchor="sw")


def main():
    parser = argparse.ArgumentParser(description="虚拟机器人 Windows 图形客户端")
    parser.add_argument("--host", default="127.0.0.1",
                        help="服务器 IP（Ubuntu 虚拟机 hostname -I 显示的地址）")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口")
    parser.add_argument("--selftest", action="store_true", help="自检模式：构建界面后立即退出")
    args = parser.parse_args()

    root = tk.Tk()
    app = RobotGUI(root, args.host, args.port)
    if args.selftest:
        # 注入模拟轨迹点，实际执行绘制逻辑（含镜头跟随，远端点在视野外也不崩溃）
        app.last_status = {"run_state": "moving", "heading": 90.0}
        app.history = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5), (0.0, 0.0),
                       (3.7, 1.2), (8.9, 4.6)]
        app.draw()
        root.update_idletasks()
        root.update()
        root.destroy()
        print("[selftest] GUI 构建成功，轨迹绘制（含镜头跟随）已执行")
        return
    root.mainloop()


if __name__ == "__main__":
    main()
