# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## 常用命令

```bash
./dev.sh          # 一键起开发环境：db 容器(5433) + 宿主 uvicorn(8100) + 宿主 Vite(5180)，已在跑的不重复启动
                  # 日志 /tmp/crm-backend.log、/tmp/crm-frontend.log；演示账号 demo / tong（密码 demo12345）

cd backend
uv sync
uv run alembic upgrade head                     # 建表
uv run python scripts/seed.py                   # 演示数据
uv run pytest                                   # 全量（依赖 db 容器在跑，测试库见下方“坑”）
uv run pytest tests/test_contacts.py            # 单文件
uv run pytest tests/test_contacts.py::test_xxx  # 单用例
uv run ruff check .                             # lint

cd frontend
npm run dev        # Vite 5180，/api 代理到 127.0.0.1:8100
npm run test       # vitest run
npm run build      # vue-tsc -b && vite build，产物 dist/ 由后端托管
```

## 架构大图

**分层模块化单体**（FastAPI），每层只依赖相邻下层，禁止跨层与环：

```
api.py（路由/鉴权/出入参）→ service.py（业务门面）→ repository.py（SQL）→ models.py（表结构）
                             ↘ app/core/（config、db、errors、security、mixins）
```

- `app/core/` 是 L0 地基；`app/services/permission.py` 是全系统**唯一判权点**（REST / MCP / 内部 agent 共用）。
- 业务代码放 `app/modules/<模块>/`，每个模块独占自己表的写权；新模块的 router 在 `app/api/v1/router.py` 挂一行。
- 依赖规则（表写权独占、跨模块读只有「调对方 service 公开函数」和「本模块 repository 只读 JOIN 对方 models」两种形态、单向无环）见 `ARCHITECTURE.md` 第 2 节，违反即架构回退。
- 层序：L0 `core`/`permission` → L1 `auth` → L2 `contacts`/`geo` → L3 `graph`/`records`/`gifts`/`funds`/`settings` → L4 `dashboard`/`ai`。`dashboard` 与 `ai` 是纯消费叶子，任何业务模块不得反向依赖。
- **纯函数子模块**（无表无状态、可独立测试）：`contacts/calendar.py`（农历↔公历）、`geo`（地理编码，key 由调用方注入）、`graph/kinship.py`（角色路径→中文称谓）。
- **唯一口径**（展示层禁止重复实现，只消费接口结果）：`display_name` → `contacts.models.Contact.display_name`；最近联系时间 → contacts repository 的 last_activity 子查询（名册过滤与 dashboard 统计共用）；权限 → `services/permission.py`。详见 `ARCHITECTURE.md` 第 6 节。
- **AI 模块**：`deepagents` 的唯一 import 点是 `backend/agent/`（可替换实现层，业务代码禁止直接 import）；对外出口为 `/mcp`（Streamable HTTP，JWT 门卫）与 `/api/v1/ai/*`（SSE 对话、写入提议确认队列、语义检索）。
- **一体化部署**：`app/main.py` 发现 `frontend/dist` 就托管 SPA 与非 `/api` 路径，生产只有一个 8100 端口。

前端（Vue 3 + Pinia）：

- `src/pages/XxxPage.vue` 与后端模块一一对应；`src/api/<模块>.ts` 同名对应后端模块，契约产物 `src/api/types.ts` 是唯一来源，禁止绕过它手写请求形状。
- 组件直接组合 Element Plus，图表统一 ECharts 5.x + echarts-gl，不重复造自研基础组件；自研部分样式只准消费 `src/design/tokens.ts` 与 `theme.ts`。

## 事实源文档（改动前先在对应文档登记）

| 要动的东西 | 事实源 |
|---|---|
| 工程规范、环境纪律、API 使用铁律 | `AGENTS.md`（已 import 到本文件） |
| 模块划分、依赖方向、表归属、接口地图 | `ARCHITECTURE.md` — 新模块**先登记再写代码** |
| 技术选型与架构决策 | `TECH_DECISIONS.md` — 新增架构决策必须同步登记 |
| 字段级数据模型 | `DATA_MODEL.md` |
| 视觉与样式 | `DESIGN.md` + `frontend/src/design/` |
| 需求与排期 | `PROJECT_BACKGROUND.md`、`ROADMAP.md` |

## 容易踩的坑

- **测试库是独立的 `personal_crm_test`**（同宿主 5433），不是开发库 `personal_crm`。`tests/conftest.py` 在 import `app` **之前**用 `setdefault` 覆盖 `DATABASE_URL`，所以改 `backend/.env` 的库名不会影响测试；往 conftest 加 import 时必须放在那段环境变量设置之后（否则会先加载到开发配置）。每个用例前 TRUNCATE 全部业务表。
- **迁移**放 `backend/alembic/versions/`（ruff 已排除该目录）：改模型后 `uv run alembic revision --autogenerate -m "..."`；新建表要连带更新 `ARCHITECTURE.md` 第 3 节的表归属。
- **`.dockerignore` 不能删**，尤其 `**/.venv` 那行：否则宿主的 macOS venv 会覆盖镜像内 `uv sync` 装好的 Linux venv，backend 容器 `Failed to spawn: alembic` 后 exit 2 静默退出。
- **镜像构建固定走阿里 PyPI 源**（清华/中科大源在 Docker Desktop VM 内取大索引页会 TLS 断开，实测不可用）；依赖在构建层已装好，所以运行期一律 `uv run --no-sync`，改 Dockerfile/compose 时别去掉 `--no-sync`。
- 本仓库已建 CodeGraph 索引（`.codegraph/`）：找符号、看调用关系与改动影响面优先 `codegraph explore "..."`，不要一上来就 grep + 逐文件读。
