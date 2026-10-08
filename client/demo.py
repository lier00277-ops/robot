# -*- coding: utf-8 -*-
"""
一键演示 / 自检脚本：依次调用全部接口并自动校验结果。
（演示视频录制、验收自测都直接用它）

用法:
    python demo.py                     # 默认连接 127.0.0.1:8000
    python demo.py --host 192.168.1.10 # 连接虚拟机

退出码: 0 = 全部通过, 1 = 存在失败
"""
import argparse
import json
import sys
import time

import requests

results = []    # (检查项名称, 是否通过, 说明)


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print("[%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail))


def req(base, method, path, payload=None, timeout=5):
    url = base + path
    if payload:
        print("\n>>> %s %s   body=%s" % (method, path, json.dumps(payload, ensure_ascii=False)))
    else:
        print("\n>>> %s %s" % (method, path))
    try:
        resp = requests.request(method, url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        print("<<< 连接失败：请先启动服务端，并确认 --host/--port 正确")
        return None, None
    print("<<< HTTP %s" % resp.status_code)
    try:
        data = resp.json()
    except ValueError:
        data = None
    print("    " + json.dumps(data, ensure_ascii=False, indent=2))
    return resp.status_code, data


def main():
    if sys.platform == "win32":
        try:    # Windows 控制台统一 UTF-8，避免中文乱码
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    parser = argparse.ArgumentParser(description="虚拟机器人接口一键演示")
    parser.add_argument("--host", default="127.0.0.1", help="服务器 IP")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口")
    args = parser.parse_args()
    base = "http://%s:%d" % (args.host, args.port)

    print("=" * 62)
    print(" 虚拟机器人设备服务 —— 接口一键演示   (服务器: %s)" % base)
    print("=" * 62)

    # 0. 心跳：确保设备在线（收到心跳后 30 秒无心跳会判定离线）
    code, data = req(base, "POST", "/heartbeat")
    record("POST /heartbeat 确保在线", code == 200)

    # 1. 服务信息
    code, data = req(base, "GET", "/")
    record("GET / 服务信息", code == 200)

    # 2. 设备状态
    code, data = req(base, "GET", "/status")
    ok = code == 200 and isinstance(data, dict) and data.get("online") is True
    record("GET /status 设备在线", ok, "运行状态=%s" % (data or {}).get("run_state"))
    if not ok:
        print("\n服务端不可用，演示终止。请先启动服务端！")
        sys.exit(1)
    x0, y0 = data["position"]["x"], data["position"]["y"]

    # 3. 传感器
    code, data = req(base, "GET", "/sensor")
    ok = code == 200 and isinstance(data, dict) and "temperature_c" in data and "imu" in data
    record("GET /sensor 传感器数据", ok)

    # 4. 运动控制 + 位置变化验证
    code, data = req(base, "POST", "/move",
                     {"direction": "forward", "speed": 0.5, "distance": 0.3})
    record("POST /move 运动控制", code == 200)
    time.sleep(1.2)
    code, data = req(base, "GET", "/status")
    x1 = (data or {}).get("position", {}).get("x", x0)
    record("位置确实发生变化", abs(x1 - x0) > 0.1, "x: %.2f -> %.2f" % (x0, x1))

    # 5. 停止设备
    code, data = req(base, "POST", "/stop")
    record("POST /stop 停止设备", code == 200 and (data or {}).get("status", {}).get("run_state") == "stopped")

    # 6. 预设任务 square：轮询观察正方形轨迹
    code, data = req(base, "POST", "/task", {"task": "square"})
    record("POST /task square 任务下发", code == 200)
    print("\n--- 轮询 /status，观察正方形轨迹演化 ---")
    for i in range(7):
        time.sleep(0.9)
        code, data = req(base, "GET", "/status")
        if data:
            print("   [t=%d] 位置=(%.2f, %.2f)  朝向=%.0f°  状态=%s" % (
                i, data["position"]["x"], data["position"]["y"],
                data["heading"], data["run_state"]))
    record("square 执行完毕自动回 idle", bool(data) and data.get("run_state") == "idle")

    # 7. patrol 持续任务 + 运行中停止
    code, data = req(base, "POST", "/task", {"task": "patrol"})
    record("POST /task patrol 持续任务", code == 200)
    time.sleep(1.5)
    code, data = req(base, "POST", "/stop")
    record("运行中 /stop 成功中断", code == 200 and (data or {}).get("status", {}).get("run_state") == "stopped")

    # 8. 非法参数 -> 422
    code, data = req(base, "POST", "/move",
                     {"direction": "forward", "speed": -1.0, "distance": 0.5})
    record("非法参数返回 422", code == 422)

    # 9. 设备忙 -> 409
    code, data = req(base, "POST", "/task", {"task": "circle"})
    time.sleep(0.2)
    code, data = req(base, "POST", "/move",
                     {"direction": "forward", "speed": 0.5, "distance": 0.3})
    record("设备忙时返回 409", code == 409)
    req(base, "POST", "/stop")

    # 10. 心跳
    code, data = req(base, "POST", "/heartbeat")
    record("POST /heartbeat 心跳上报", code == 200)

    # 汇总
    print("\n" + "=" * 62)
    failed = [r for r in results if not r[1]]
    print(" 汇总: %d 项通过, %d 项失败" % (len(results) - len(failed), len(failed)))
    for name, ok, detail in results:
        if not ok:
            print("   FAIL: %s  %s" % (name, detail))
    print("=" * 62)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
