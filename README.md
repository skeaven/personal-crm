# Personal CRM（个人名册）

从零自研的家庭个人关系管理系统：中文一等公民（中文姓名 / 农历日期）、知识图谱式关系、AI 原生录入（DeepAgents + MCP）、家庭共享与权限隔离。

当前状态：**L1–L4 全部落地**（通讯录 / 关系图谱 / 时间与生活流 / AI 能力），L5（迁移与打磨）未开工。详见 [ROADMAP.md](./ROADMAP.md)。

## 文档导航

| 文档 | 内容 |
|---|---|
| [PROJECT_BACKGROUND.md](./PROJECT_BACKGROUND.md) | 项目缘起、Monica 调研、需求基线 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | **结构事实源**：模块清单、依赖方向、表归属、接口地图 |
| [TECH_DECISIONS.md](./TECH_DECISIONS.md) | 全部技术决策（ADR 式，含理由） |
| [DATA_MODEL.md](./DATA_MODEL.md) | 字段级数据模型 |
| [ROADMAP.md](./ROADMAP.md) | 5 级实现路线图与当前进度 |
| [DESIGN.md](./DESIGN.md) | 前端设计系统（风格锁定） |
| [AGENTS.md](./AGENTS.md) | 工程规范（agent 开发必读） |

## 功能概览

- **名册**：联系人 CRUD（中文姓名单字段，D23）、direct/edge 双层与升级、同名检测、私密/家庭可见两档权限。
- **关系图谱**：角色化关系边（from_role/to_role）、中文称谓与辈分推导、递归 CTE 的 N 度展开、echarts-gl 3D 图。
- **时间与生活流**：公历/农历重要日期（lunar-python）、活动（含图片与参与者）、待办、备注、礼物与人情、资金往来、联系人详情页往来 Tab。
- **主动提醒**：三源扫描（重要日期 / 任务 / 还款）幂等重建 + 进程内 1h 调度，应用内通知（D22）。
- **概览首页**：待办四桶聚合、统计卡、跳转过滤。
- **AI**：LLM/Embedding/高德 key 配置页、`/mcp` 端点（个人访问令牌）、SSE 助理对话（会话持久化）、截图导入、pgvector 语义检索。
- **地图**：高德地理编码（静态市县区坐标表降级），省份 choropleth + 坐标散点。

## 技术栈

- 后端：Python 3.12 / FastAPI / SQLAlchemy 2（async + asyncpg）/ Alembic / pytest / ruff
- AI：DeepAgents + LangGraph（PostgreSQL checkpointer）/ MCP（Streamable HTTP）/ pgvector
- 前端：Vue 3 / Vite / Pinia / **Element Plus** / **ECharts 5.x + echarts-gl** / vitest
- 数据库：PostgreSQL 16（`pgvector/pgvector:pg16` 镜像，语义检索已启用）
- 部署：docker-compose 一体化（FastAPI 托管前端构建产物，单端口）

## 本地开发

```bash
./dev.sh          # 一键起开发环境：db 容器(5433) + 宿主 uvicorn(8100) + 宿主 Vite(5180)
                  # 已在跑的服务不会重复启动；日志 /tmp/crm-backend.log、/tmp/crm-frontend.log
```

- 前端 http://localhost:5180（`/api` 代理到 127.0.0.1:8100）
- 演示账号：`demo` / `tong`，密码 `demo12345`（由 `scripts/seed.py` 写入）

手动分步（`./dev.sh` 做的就是这些）：

```bash
docker compose up -d db                     # 数据库容器，宿主机端口 5433

cd backend                                  # 后端
uv sync
uv run alembic upgrade head                 # 建表
uv run python scripts/seed.py               # 演示数据
uv run uvicorn app.main:app --port 8100 --reload

cd frontend && npm install && npm run dev   # 前端
```

> 环境纪律（见 AGENTS.md）：开发用宿主进程，测试环境的 `backend` 容器必须停掉（`docker compose stop backend`），否则两者抢 8100；`db` 容器全程共享。

## 测试

```bash
cd backend  && uv run pytest && uv run ruff check .
cd frontend && npm run test && npm run build
```

后端测试库为独立的 `personal_crm_test`（同宿主 5433），不会碰开发库。

## 部署（docker-compose 一体化）

```bash
docker compose up -d --build                # 默认对外 8100
```

生产覆盖层只对外 80 端口（`JWT_SECRET` 写入同目录 `.env`）：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# 访问 http://<host>:80（FastAPI 同时托管 API 与前端页面，同源）
```

容器启动即自动执行 `alembic upgrade head` 与 `scripts/seed.py`；上传目录为 named volume。
