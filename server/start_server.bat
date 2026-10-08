@echo off
REM ============================================================
REM  Windows 本地调试启动脚本（正式环境请使用 Ubuntu 的 run.sh）
REM ============================================================
cd /d %~dp0
if not exist venv (
    echo [1/2] 创建虚拟环境并安装依赖...
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)
echo [2/2] 启动服务: http://0.0.0.0:8000  （接口文档: /docs）
venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000
