#!/usr/bin/env bash
# One-command startup: backend (FastAPI :8000) + frontend (Vite :3000).
# Usage: bash dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "→ 启动后端 (uvicorn :${BACKEND_PORT})..."
cd "$ROOT/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACK_PID=$!

echo "→ 启动前端 (vite :${FRONTEND_PORT})..."
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "  (首次运行安装前端依赖)"
  npm install --no-audit --no-fund
fi
npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" &
FRONT_PID=$!

trap 'echo "→ 停止服务..."; kill $BACK_PID $FRONT_PID 2>/dev/null || true' EXIT INT TERM

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  前端:  http://localhost:${FRONTEND_PORT}"
echo "  后端:  http://localhost:${BACKEND_PORT}/docs"
echo "  停止:  Ctrl+C"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

wait