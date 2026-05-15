#!/bin/bash

# 启动后端
echo "🚀 正在启动后端服务 (FastAPI)..."
cd backend
source venv/bin/activate
python3 -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# 启动前端
echo "🎨 正在启动前端服务 (Vite)..."
cd ../frontend
npm run dev -- --port 5173 &
FRONTEND_PID=$!

echo "✅ 服务已启动！"
echo "🌐 前端地址: http://localhost:5173"
echo "🔌 后端接口: http://localhost:8000"
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
