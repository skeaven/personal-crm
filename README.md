# Personal CRM（个人名册）

从零自研的家庭个人关系管理系统：中文一等公民（中文姓名 / 农历日期）、知识图谱式关系、AI 原生录入（DeepAgents + MCP）、家庭共享与权限隔离。

## 文档导航

| 文档 | 内容 |
|---|---|
| [PROJECT_BACKGROUND.md](./PROJECT_BACKGROUND.md) | 项目缘起、Monica 调研、需求基线 |
| [TECH_DECISIONS.md](./TECH_DECISIONS.md) | 全部技术决策（ADR 式，含理由） |
| [DATA_MODEL.md](./DATA_MODEL.md) | 字段级数据模型 |
| [ROADMAP.md](./ROADMAP.md) | 5 级实现路线图 |
| [DESIGN.md](./DESIGN.md) | 前端设计系统（风格锁定） |
| [AGENTS.md](./AGENTS.md) | 工程规范（agent 开发必读） |

## 技术栈

- 后端：Python 3.12 / FastAPI / SQLAlchemy 2 / Alembic / pytest
- 前端：Vue 3 / Vite / Pinia / Naive UI / vitest
- 数据库：PostgreSQL 16（pgvector 预留）
- 部署：docker-compose 一体化（FastAPI 托管前端构建产物，端口 8100）

## 本地开发

```bash
# 1. 起数据库
docker compose up -d db

# 2. 后端（backend/ 目录）
uv sync
uv run alembic upgrade head          # 建表
uv run python scripts/seed.py        # 演示数据：demo / tong，密码 demo12345
uv run uvicorn app.main:app --port 8100 --reload

# 3. 前端（frontend/ 目录，另一终端）
npm install
npm run dev                          # http://localhost:5180（/api 代理到 8100）

# 测试
cd backend  && uv run pytest && uv run ruff check .
cd frontend && npm run test && npm run build
```

## 生产部署（NAS）

```bash
docker compose up -d --build
# 访问 http://<nas-ip>:8100（FastAPI 托管 API 与前端页面，同源）
```
