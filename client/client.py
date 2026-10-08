# -*- coding: utf-8 -*-
"""
Windows 菜单式命令行客户端
（灵境竞赛组-物联网方向-第一阶段考核）

用法:
    python client.py                      # 交互菜单，默认连接 127.0.0.1:8000
    python client.py --host 192.168.1.10  # 连接虚拟机（Ubuntu hostname -I 显示的 IP）
"""
import argparse
import json
import sys

import requests

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

DIRECTIONS = ("forward", "backward", "left", "right")
TASKS = ("forward", "square", "circle", "triangle", "patrol")


class RobotClient:
    """命令行客户端：requests 调用服务端全部接口。"""

    def __init__(self, host, port):
        self.base = "http://%s:%d" % (host, port)

    def call(self, method, path, payload=None):
        """统一请求入口，返回 (状态码, 数据) 或 (None, None)。"""
        try:
            resp = requests.request(method, self.base + path, json=payload, timeout=5)
        except requests.exceptions.ConnectionError:
            print("\n[连接失败] 无法连接 %s" % self.base)
            print("  请检查: 1) Ubuntu 服务是否已启动")
            print("          2) IP/端口是否正确（虚拟机里 hostname -I 查询）")
            print("          3) 网络是否互通（Windows 上 ping 虚拟机 IP）")
            print("          4) 防火墙是否放行 8000 端口")
            return None, None
        except requests.exceptions.Timeout:
            print("\n[超时] 请求 %s 超过 5 秒未响应" % path)
            return None, None
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        return resp.status_code, data

    @staticmethod
    def show(tag, result):
        """格式化打印接口结果。"""
        code, data = result
        if code is None:
            return
        mark = "成功" if 200 <= code < 300 else "失败"
        print("\n【%s】HTTP %s (%s)" % (tag, code, mark))
        print(json.dumps(data, ensure_ascii=False, indent=2))

    # ---------------- 交互菜单 ----------------
    def menu(self):
        while True:
            print("\n" + "=" * 52)
            print("  虚拟机器人控制台    服务器: %s" % self.base)
            print("=" * 52)
            print("  1. 查询设备状态    GET  /status")
            print("  2. 查询传感器数据  GET  /sensor")
            print("  3. 运动控制        POST /move")
            print("  4. 执行预设任务    POST /task")
            print("  5. 停止设备        POST /stop")
            print("  6. 心跳上报        POST /heartbeat")
            print("  0. 退出")
            try:
                choice = input("请选择: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                return
            if choice == "1":
                self.show("设备状态", self.call("GET", "/status"))
            elif choice == "2":
                self.show("传感器数据", self.call("GET", "/sensor"))
            elif choice == "3":
                self.do_move()
            elif choice == "4":
                self.do_task()
            elif choice == "5":
                self.show("停止设备", self.call("POST", "/stop"))
            elif choice == "6":
                self.show("心跳上报", self.call("POST", "/heartbeat"))
            elif choice == "0":
                print("再见！")
                return
            else:
                print("无效选择，请重新输入")

    def do_move(self):
        direction = input("方向 %s [forward]: " % "/".join(DIRECTIONS)).strip() or "forward"
        if direction not in DIRECTIONS:
            print("方向不合法，可选: %s" % "/".join(DIRECTIONS))
            return
        try:
            speed = float(input("速度 m/s [0.5]: ").strip() or "0.5")
            distance = float(input("距离 m [0.5]: ").strip() or "0.5")
        except ValueError:
            print("速度和距离必须是数字")
            return
        self.show("运动控制", self.call(
            "POST", "/move", {"direction": direction, "speed": speed, "distance": distance}))

    def do_task(self):
        task = input("任务 %s [square]: " % "/".join(TASKS)).strip() or "square"
        if task not in TASKS:
            print("任务不合法，可选: %s" % "/".join(TASKS))
            return
        self.show("预设任务", self.call("POST", "/task", {"task": task}))


def main():
    if sys.platform == "win32":
        try:    # Windows 控制台统一 UTF-8，避免中文乱码
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    parser = argparse.ArgumentParser(description="虚拟机器人 Windows 命令行客户端")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="服务器 IP（Ubuntu 虚拟机 hostname -I 显示的地址）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="服务器端口")
    args = parser.parse_args()
    RobotClient(args.host, args.port).menu()


if __name__ == "__main__":
    main()
