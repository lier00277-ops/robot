#!/usr/bin/env bash
# ============================================================
#  虚拟机器人设备服务 —— Ubuntu 一键启动脚本
#  用法: bash run.sh    （或 ./run.sh，需先 chmod +x run.sh）
# ============================================================
set -e
cd "$(dirname "$0")"

# 1) 首次运行：创建虚拟环境并安装依赖
if [ ! -d venv ]; then
    echo "[1/3] 创建虚拟环境并安装依赖..."
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
else
    echo "[1/3] 虚拟环境已存在，跳过安装"
fi

# 2) 显示本机 IP（Windows 客户端要填的地址）
echo "[2/3] 本机局域网 IP（Windows 客户端请填第一个 IPv4 地址）:"
hostname -I

# 3) 启动服务：必须监听 0.0.0.0，才能被局域网内 Windows 访问
echo "[3/3] 启动服务: http://0.0.0.0:8000   （接口文档: http://<IP>:8000/docs）"
exec ./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
