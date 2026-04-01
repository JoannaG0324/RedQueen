#!/bin/bash

# 启动RedQueen后端服务

# 设置环境变量
export PYTHONPATH=$(pwd)/src

# 检查是否安装了必要的依赖
if ! command -v pip &> /dev/null; then
    echo "Error: pip is not installed"
    exit 1
fi

# 安装依赖
echo "Installing dependencies..."
pip install -r requirements.txt

# 启动服务
echo "Starting RedQueen backend service..."
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
