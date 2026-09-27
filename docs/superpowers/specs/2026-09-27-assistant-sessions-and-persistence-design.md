# AI 助理：独立页面 + 会话持久化 设计

> 日期：2026-09-27｜状态：待用户审阅
> 上游：`PROJECT_BACKGROUND.md`（R3 AI 原生录入）、`TECH_DECISIONS.md`（D6 AI 接入、D11 MCP）
> 本文是实施计划的输入；批准后进入 `writing-plans`。

## 1. 目标（用户原话拆解）

1. 去掉 AI 助理的**悬浮窗**。
2. 助理页面放到导航里**主页的下面**（与主页同级），是**单独的页面**。
3. 要有**对话的历史记录**：前端生成会话标识，后端按它存储。
4. 改造成**流式输出**。
5. 要能**看到工具调用**。

## 2. 现状核对（重要：4、5 已基本具备）

调研结论——本次是**补齐**，不是重写：

| 需求 | 现状 |
|---|---|
| 流式输出 | ✅ 已有：`agent/runner.py` 的 `stream_agent` 走 `astream` 逐块 yield；`/ai/chat` 返回 SSE；前端 `aiApi.chat` 带事件回调 |
| 看到工具调用 | ✅ 已有：后端 yield `{"type":"tool","name"}`，前端渲染成 tag（但无「进行中」状态） |
| 多轮记忆 | ⚠️ 有，但 `InMemorySaver` 是**进程内内存**，重启即丢 |
| 独立页面 | ✅ 已有 `ChatPage.vue`（`/assistant` 路由） |
| 导航入口 | ❌ `navItems` 里没有「助理」 |
| 去悬浮窗 | ❌ `AppLayout` 的 `ai-fab` + `ai-float` 仍在 |
| 前端生成标识 | ⚠️ 现在是前端传 `null`、后端生成后回传，与需求相反 |
| 会话列表 UI | ❌ 无 |

## 3. 命名分层（用户 2026-09-27 纠正）

`thread` 是 LangGraph 的概念，业务侧不跟着叫：

| 层 | 概念 | 命名 |
|---|---|---|
| 前端 / 业务 | 一次对话 | **session**：`session_id`，前端 `crypto.randomUUID()` 生成 |
| 数据库 | 会话索引 | 表 **`ai_sessions`**（`session_id` / `user_id` / `title` / 时间） |
| API | 请求与路由 | `ChatIn.session_id`、`GET|DELETE /ai/sessions`、`GET /ai/sessions/{id}/messages` |
| agent 层（内部实现细节） | LangGraph 的 thread | `thread_id`，**只出现在 `runner.py`**，由 `f"{user.id}:{session_id}"` 拼成 |

`thread_id` 不出现在表名、路由、前端类型或 API 契约里。

## 4. 前端设计

- **删悬浮窗**：`AppLayout` 的 `ai-fab` / `ai-float` / `.fab-*` / `.ai-float*` 样式与 `chatOpen` 状态整体移除；`AgentChat` 只由 `ChatPage` 使用（`AppLayout` 不再 import 它）。
- **导航**：`navItems` 第 2 位（主页之后）加 `{ key: 'assistant', label: '助理', icon: Sparkles, to: '/assistant' }`。
- **ChatPage 两栏**：左侧会话列表（新建 / 切换 / 删除，显示标题与最后活跃时间），右侧对话区；窄屏退化为顶部下拉切换。
- **session_id 前端生成**：点「新对话」→ `crypto.randomUUID()`；首条消息随请求带上。切回旧会话时用 `GET /ai/sessions/{id}/messages` 拉历史。
- **工具调用**：流式过程中显示「正在调用 X…」进行中态，结束后落到历史消息的工具 tag 列表里（tag 渲染已存在）。
- **空列表**：还没有任何会话时，进入页面直接开一个新对话（前端立即生成 `session_id`），不出现空列表页。

## 5. 后端设计

### 5.1 checkpointer 换成持久化

`AsyncPostgresSaver`（`langgraph-checkpoint-postgres`）：

- **新增依赖** `langgraph-checkpoint-postgres`，它带 `psycopg`(3) + `psycopg-pool`。
- **生命周期**：`from_conn_string` 是 async context manager，不适合每请求建连 → 在 `create_app()` 的 lifespan 里建立并长期持有（与已有的一次性 `cleanup_temp()` 调用同一处），把实例注入 runner，取代模块级 `_CHECKPOINTER = InMemorySaver()`。
- **必须 `setup()`**：首次使用要调 `.setup()` 建它自己的表（官方 README 明确要求）。
- **连接串从现有 `DATABASE_URL` 派生**（去掉 `+asyncpg` 方言前缀），**不新增配置项**；若手动建连需 `autocommit=True` + `row_factory=dict_row`（官方要求，否则 `.setup()` 不落盘、按列名取值会 TypeError）。
- **代价（已知并接受）**：引入第二个数据库驱动（psycopg3 与现有 asyncpg 并存，前者只服务 checkpointer）。这是 LangGraph 的既定实现方式；替代是 SQLite 文件存储，但会破坏 D3「单库」决策，故不取。
- **换掉即丢的历史**：现存内存态历史无法迁移（它本来也在重启时丢），无实际损失。

### 5.2 会话索引表 `ai_sessions`（归 ai 模块）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `session_id` | VARCHAR(64) | **PK** | 前端生成的 uuid；业务标识 |
| `user_id` | BIGINT | FK users(id), index | 归属者，会话按用户隔离 |
| `title` | VARCHAR(100) | NOT NULL | 取首条用户消息的前若干字 |
| `created_at` / `updated_at` | TIMESTAMPTZ | server_default now() | 最后活跃时间用于列表排序 |

**主键取舍**：D15 定的是「业务实体主键保持 BIGINT」，但会话标识天然是前端生成的 uuid 且唯一，故 `session_id` 直接做主键——少一列少一个索引，语义更直接（用户 2026-09-27 确认）。

**索引行不需要单独的创建端点**：第一轮 chat 发现 `session_id` 不存在就顺手建（少一个接口、少一次往返）。

### 5.3 端点

| 端点 | 作用 |
|---|---|
| `GET /ai/sessions` | 我的会话列表（按最后活跃倒序） |
| `DELETE /ai/sessions/{session_id}` | 删会话，同时清 checkpointer 里的对应数据 |
| `GET /ai/sessions/{session_id}/messages` | 切换会话时读历史消息（从 checkpointer 的 state 里取） |
| `POST /ai/chat` | 已有；`ChatIn` 的 `thread_id` 改为 `session_id`（无则前端生成） |

**实现说明（已查官方文档核实）**：

- **删会话**：`await checkpointer.adelete_thread(thread_id)`（`BaseCheckpointSaver` 规定的异步清理接口）。
- **读历史**：`await checkpointer.aget_tuple({"configurable": {"thread_id": tid}})`，消息在 `checkpoint["channel_values"]["messages"]`；归一为 `[{role, content, tools}]` 形状后返回，前端按同一形状渲染。
- **建索引行**：在 SSE 的 `event_stream` 内、调用 agent **之前** upsert（`ON CONFLICT DO NOTHING`，已存在不动），标题取本次用户消息前 30 字（去掉换行符）。

**破坏性变更（显式声明）**：`ChatIn` 的 `thread_id` 字段更名为 `session_id`，前端同步改，旧字段不再接受。

**跨用户隔离是红线**：三个新端点与 chat 都必须校验 `session_id` 归属当前用户，否则按 404 处理（不泄露存在性）——与项目既有的权限口径一致。

### 5.4 运行时配置

`AsyncPostgresSaver` 未配置（如 LLM 未配置）时的降级沿用现有 `LLMNotConfiguredError` 的 SSE error 帧路径；checkpointer 不可用不应让整个应用起不来。

## 6. 测试策略（TDD）

- **后端**：会话索引的增删查；**跨用户隔离**（A 读不到 / 删不掉 B 的会话，历史消息同样）；首轮 chat 自动建索引；历史消息读取形状；标题截取规则。checkpointer 相关测试用测试库的同一 PostgreSQL。
- **前端**：会话列表组件的新建 / 切换 / 删除交互；`session_id` 由前端生成（不再依赖后端回传）。
- 完成前跑 `uv run pytest && uv run ruff check .` 与 `npm run test && npm run build`。

## 7. 文档同步（AGENTS.md 硬约束）

- `TECH_DECISIONS.md`：新增 **D20 助理会话持久化**（session/thread 分层命名、AsyncPostgresSaver、ai_sessions 表）。
- `ARCHITECTURE.md`：ai 模块表归属加 `ai_sessions`；接口地图补三个端点；第 6 节唯一口径视需要补「会话与历史」。
- `DESIGN.md`：助理页两栏布局与会话列表的视觉规则；**移除悬浮球相关描述**（若有）。

## 8. 不做的事（明确排除）

- 不重写流式与工具调用（已可用，只补「进行中」状态）。
- 不做会话重命名、置顶、搜索（YAGNI，需要时再加）。
- 不做消息级编辑 / 重新生成。
- 不做多设备实时同步（会话按用户隔离，多端各自可见同一份数据即可，不做推送）。
- 不迁移现存内存态历史。
