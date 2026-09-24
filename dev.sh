#!/usr/bin/env bash
# 本地开发启动脚本：确保 PostgreSQL（docker）+ 后端 8100 + 前端 5180 全部就绪。
# 用法：./dev.sh        （已在跑的服务不会重复启动）

set -e
cd "$(dirname "$0")"

# 数据库：docker compose 里的 personal-crm-db（宿主机端口 5433）
if ! docker compose ps --status running db 2>/dev/null | grep -q personal-crm-db; then
  echo "[dev] 启动数据库…"
  docker compose up -d db >/dev/null
  for _ in $(seq 1 20); do
    docker compose exec -T db pg_isready -U crm -d personal_crm >/dev/null 2>&1 && break
    sleep 2
  done
fi
echo "[dev] 数据库就绪（5433）"

# 后端：uvicorn 8100
if ! lsof -ti :8100 >/dev/null 2>&1; then
  echo "[dev] 启动后端（8100）…"
  (cd backend && nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8100 > /tmp/crm-backend.log 2>&1 &)
  sleep 3
fi
curl -sf http://127.0.0.1:8100/api/v1/health >/dev/null && echo "[dev] 后端就绪（http://127.0.0.1:8100）" \
  || { echo "[dev] 后端启动失败，日志：tail /tmp/crm-backend.log"; exit 1; }

# 前端：Vite 5180
if ! lsof -ti :5180 >/dev/null 2>&1; then
  echo "[dev] 启动前端（5180）…"
  (cd frontend && nohup npm run dev > /tmp/crm-frontend.log 2>&1 &)
  sleep 3
fi
curl -sf -o /dev/null http://localhost:5180/ && echo "[dev] 前端就绪（http://localhost:5180）" \
  || { echo "[dev] 前端启动失败，日志：tail /tmp/crm-frontend.log"; exit 1; }

echo "[dev] 全部就绪。登录账号：demo / tong（密码 demo12345）"
