# 虚拟机器人设备服务

**灵境竞赛组 · 物联网方向 · 第一阶段考核**

在 Ubuntu 虚拟机中使用 **Python + FastAPI** 搭建"虚拟机器人设备服务"，Windows 端作为客户端，通过局域网访问该服务，完成设备状态查询与控制。

---

## 架构总览

```
┌──────────────────────────┐        局域网 HTTP         ┌──────────────────────────┐
│  Ubuntu 虚拟机（服务端）   │◄─────────────────────────►│  Windows 本地（客户端）    │
│  server/                 │                            │  client/                 │
│  FastAPI + uvicorn       │   GET  /status /sensor     │  client.py    命令行菜单  │
│  监听 0.0.0.0:8000       │   POST /move /stop /task   │  gui_client.py 图形+轨迹   │
│  状态实时持久化到 JSON    │   POST /heartbeat          │  demo.py      一键演示    │
└──────────────────────────┘                            └──────────────────────────┘
```

## 目录结构

```
robot/
├── server/                       # Ubuntu 虚拟机端
│   ├── robot.py                  # 设备层：状态机、运动模拟、传感器、JSON 持久化
│   ├── main.py                   # 通信层：FastAPI 应用，注册全部接口
│   ├── requirements.txt          # fastapi、uvicorn
│   ├── run.sh                    # Ubuntu 一键启动脚本
│   ├── start_server.bat          # Windows 本地调试启动脚本（可选）
│   └── device_state.json         # 运行时自动生成：保存当前设备状态
├── client/                       # Windows 端
│   ├── client.py                 # 菜单式命令行客户端
│   ├── gui_client.py             # Tkinter 图形客户端（含轨迹可视化）
│   ├── demo.py                   # 一键演示/自检脚本（录视频也用）
│   └── requirements.txt          # requests
├── docs/
│   ├── 演示视频录制教程.md         # 分镜脚本 + 录屏工具步骤
│   └── 演示讲解稿.md               # 逐段口播稿
└── README.md                     # 本文件
```

---

## 一、运行环境

| 端 | 系统 | 软件 | 依赖包 |
|---|---|---|---|
| 服务端 | Ubuntu 虚拟机 | Python 3.9+ | fastapi、uvicorn |
| 客户端 | Windows | Python 3.9+ | requests（Tkinter 为 Python 自带） |

---

## 二、Ubuntu 服务端部署（考核环境）

### 2.1 虚拟机网络设置（重要）

建议使用**桥接模式**，让虚拟机直接获得局域网 IP，Windows 无需任何转发配置即可访问：

- VMware：虚拟机设置 → 网络适配器 → 桥接模式（自动）
- VirtualBox：设置 → 网络 → 连接方式选"桥接网卡"

> 若只能使用 NAT，需要在虚拟机设置中添加端口转发：主机 8000 → 虚拟机 8000。

### 2.2 上传代码并启动

```bash
# 1. 将 robot/server/ 目录上传到虚拟机（共享文件夹 / scp / git 均可）
# 2. 进入目录，一键启动
cd server
bash run.sh
```

`run.sh` 会自动完成：创建虚拟环境 → 安装依赖（清华镜像）→ 显示本机 IP → 以 `0.0.0.0:8000` 启动。

手动启动方式（不使用脚本时）：

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
uvicorn main:app --host 0.0.0.0 --port 8000
```

> ⚠️ 必须监听 `0.0.0.0`，只监听 `127.0.0.1` 时 Windows 无法访问。

### 2.3 查询虚拟机 IP

```bash
hostname -I    # 例如输出 192.168.1.100
```

### 2.4 验证与防火墙

- 浏览器访问 `http://192.168.1.100:8000/docs`，能看到 Swagger 接口文档即成功；
- 若 Windows 连不上：`sudo ufw allow 8000`（若启用了 ufw），或临时 `sudo ufw disable`。

---

## 三、Windows 客户端使用

### 3.1 安装依赖

```bat
cd client
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3.2 命令行客户端

```bat
python client.py --host 192.168.1.100     REM 换成虚拟机 IP
```

交互菜单：`1` 状态查询 / `2` 传感器 / `3` 运动控制 / `4` 预设任务 / `5` 停止 / `6` 心跳 / `0` 退出。

### 3.3 图形客户端（含轨迹可视化）

```bat
python gui_client.py --host 192.168.1.100
```

左侧按钮调用各接口，右侧画布每 400ms 轮询 `/status`，实时绘制机器人位置、朝向和行进轨迹（1 格 = 1 米），底部显示请求/响应日志。

### 3.4 一键演示（录视频 / 验收自测）

```bat
python demo.py --host 192.168.1.100
```

自动依次调用全部接口、轮询展示正方形轨迹、演示停止中断与错误处理，最后输出 PASS/FAIL 汇总。

---

## 四、接口文档

| 接口 | 方法 | 功能 | 请求体 |
|---|---|---|---|
| `/status` | GET | 设备在线状态、运行状态、实时位置 | — |
| `/sensor` | GET | 模拟传感器数据 | — |
| `/move` | POST | 运动控制 | `{direction, speed, distance}` |
| `/stop` | POST | 停止设备 | — |
| `/task` | POST | 预设任务 | `{task}` |
| `/heartbeat` | POST | 心跳上报（附加加分接口） | — |

### GET /status

```json
{
  "device_id": "robot-001",
  "online": true,
  "run_state": "idle",           // offline / idle / moving / executing_task / stopped
  "current_task": null,
  "position": {"x": 1.17, "y": 0.05},
  "heading": 46.0,
  "speed": 0.0,
  "battery": 96.8,
  "uptime_sec": 4.9
}
```

### GET /sensor

```json
{
  "temperature_c": 31.86,        // 运行时基准升高 8℃，叠加随机扰动
  "humidity_pct": 46.51,
  "battery_voltage_v": 12.57,
  "obstacle_distance_cm": 255.8,
  "imu": {"ax": -0.018, "ay": -0.004, "az": 9.819, "gyro_z_deg_s": 0.35},
  "wheel_speed_rpm": -1.8
}
```

### POST /move

请求体（全部有校验，非法值返回 422）：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| direction | string | forward/backward/left/right | 方向（left=左转 90°（逆时针）、right=右转，均先原地转向再前进） |
| speed | float | (0, 2] m/s | 速度 |
| distance | float | (0, 5] m | 距离 |

```bash
curl -X POST http://<IP>:8000/move -H "Content-Type: application/json" \
     -d '{"direction":"forward","speed":0.5,"distance":0.3}'
```

响应：`{"message":"运动指令已下发","move":{...},"status":{...}}`

### POST /stop

中断正在进行的运动/任务，设备进入 `stopped` 状态。设备忙时也可调用（幂等）。

### POST /task

| 任务 | 轨迹 |
|---|---|
| forward | 前进 0.5 m |
| square | 正方形：4×0.5 m 直行 + 4×90° 转弯 |
| circle | 半径 0.5 m 圆形：36 段微步 |
| triangle | 三角形：3×0.5 m 直行 + 3×120° 转弯 |
| patrol | 持续巡逻（0.8 m 直行 + 90° 转弯循环），直到 /stop |

任务执行期间 `run_state=executing_task`，完成后自动回到 `idle`；设备忙时下发新指令返回 **409**。

### POST /heartbeat（附加）

刷新心跳时间戳。服务端在收到过心跳后，超过 30 秒未再收到心跳会判定设备离线（`online=false`），体现"在线状态"的真实语义。

---

## 五、设计要点

### 5.1 设备状态机

```
             power_on                    /move /task
 offline ──────────────► idle ────────────────────────► moving / executing_task
                            ▲                                │
                            │        任务完成 / 移动完成       │ /stop
                            └────────────────────────────────┴──────► stopped
```

### 5.2 运动模拟（10Hz）

运动由 asyncio 后台任务按真实时间演化：每 0.1s 依据速度、朝向更新坐标，`/stop` 可随时中断（并发安全，任务取消后正确清理状态）。

### 5.3 传感器"物理联动"

传感器 = 基准值 + 随机扰动，且与设备状态联动：运行时电机温度升高、转弯时 IMU 角速度不为零、电量随运行缓慢下降、电压与电量对应——模拟的是"一台设备"，而不是随机数生成器。

### 5.4 状态持久化

每次状态变更节流写入 `device_state.json`（运动中 0.5s/次，状态切换立即写），服务重启自动恢复位置、朝向、电量，落实"服务端能够保存并更新当前设备状态"。

### 5.5 分层设计

`robot.py`（设备层）与 `main.py`（通信层）完全解耦——真实 IoT 场景中，HTTP 可替换为 MQTT/CoAP 而设备层不动，这一层即"设备影子（Device Shadow）"。

---

## 六、考核点对照表

| 题目要求 | 实现位置 | 验证方式 |
|---|---|---|
| /status 返回在线、运行状态 | `main.py get_status` + `robot.status()` | demo 第 2 项 |
| /sensor 模拟传感器（固定或随机） | `robot.sensors()` 基准值+随机扰动 | demo 第 3 项 |
| /move 接收运动控制参数 | `main.py move` + Pydantic 校验 | demo 第 4 项（位置真实变化） |
| /stop 停止设备 | `main.py stop` + 任务取消 | demo 第 5、7 项 |
| /task 预设任务（forward、square 等） | `robot._execute_task()` 路径规划 | demo 第 6 项（轨迹轮询） |
| 服务端保存并更新当前设备状态 | 内存状态机 + `device_state.json` | 重启服务位置/电量恢复 |
| Windows 端完成接口调用 | client.py / gui_client.py / demo.py | 全部实测通过 |
| README 说明环境、启动、接口 | 本文件 | — |

---

## 七、常见问题

**Q1：Windows 连不上虚拟机服务？**
1. 确认服务端用 `--host 0.0.0.0` 启动；2. Windows `ping 虚拟机IP` 是否通；3. 虚拟机网络是否为桥接；4. 防火墙放行 8000。

**Q2：Ubuntu 上 pip 报 externally-managed-environment？**
按 2.2 节先创建 venv 再安装（Ubuntu 24.04 强制要求）。

**Q3：客户端提示 409？**
设备正在运动/执行任务，先调用 `/stop`（这是预期行为，不是 bug）。

**Q4：`/move` 返回 422？**
参数越界（速度 ≤0 或 >2，距离 ≤0 或 >5，方向拼写错误），按接口文档修正。

**Q5：想重置设备状态？**
删除 `server/device_state.json` 后重启服务即可回到原点。

---

## 八、演示视频（预留）

`client/demo.py` 一条命令跑完全部接口演示，录制视频时直接使用；分镜与口播稿见 `docs/演示视频录制教程.md`、`docs/演示讲解稿.md`。
