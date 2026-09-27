# 助理独立页面与会话持久化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 去掉 AI 悬浮球、把助理提升为导航中的独立页面，会话按前端生成的 `session_id` 持久化（LangGraph Postgres checkpointer + 轻量索引表），支持会话列表、切换、删除与历史消息回看。

**Architecture:** 后端把 `InMemorySaver` 换成 `AsyncPostgresSaver`（在 lifespan 中长生命周期持有，测试与降级路径仍退回内存态），新增 `ai_sessions` 轻量索引表承载列表/标题/活跃时间；前端 `session_id` 由 `crypto.randomUUID()` 生成，ChatPage 改两栏（会话列表 + 对话区）。流式与工具调用已可用，本次只补「进行中」状态与历史渲染。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / Alembic / langgraph-checkpoint-postgres（psycopg3）；Vue 3 / Element Plus / Pinia / vitest。

**Spec:** `docs/superpowers/specs/2026-09-27-assistant-sessions-and-persistence-design.md`

## Global Constraints

- 工程规范以 `AGENTS.md` 为准：每个方法只做一个抽象层级、每个方法必须有注释（写「为什么」）、命名见名知义、TDD 先行。
- 架构规则以 `ARCHITECTURE.md` 为准：表写权独占；`backend/agent/` 是 **deepagents 的唯一 import 点**，业务代码禁止直接 import。
- 权限一律经 `app/services/permission.py`；错误一律用 `app/core/errors.py` 的 `ValidationError`(422) / `NotFoundError`(404)。
- **跨用户隔离是红线**：会话的读/删/历史都必须校验归属，不属于当前用户一律按 404 处理（不泄露存在性）。
- **命名分层**（用户 2026-09-27 纠正）：业务与前端用 **session**（`session_id`）；**thread_id 只允许出现在 `agent/runner.py` 内部**，由 `f"{user.id}:{session_id}"` 拼成；不得出现在表名、路由、前端类型或 API 契约里。
- `session_id` 直接做主键（VARCHAR），不加自增 id 列——用户 2026-09-27 确认。
- 后端命令在 `backend/` 下：`uv run pytest`、`uv run ruff check .`（line-length 100）。前端在 `frontend/` 下：`npm run test`、`npm run build`（`npx vue-tsc -b --noEmit` 在本项目不可用）。
- 前端视觉只消费 `frontend/src/design/tokens.ts`；表单弹窗统一 `el-dialog` 480px（D16/D17）。
- **不要** rebuild 镜像、不要重启测试/生产环境、不要在测试环境跑迁移（`AGENTS.md` 环境纪律）。
- `dev.sh` 起的 uvicorn **没有 `--reload`**：改完后端必须重启它，否则验证的是旧代码。

## Review Focus

以下五类最容易让真实用户踩坑，各自已钉到对应任务的测试里：

1. **越权读别人的会话**：A 拿到 B 的 `session_id` 去读历史或删除——必须 404（Task 3 的端点、Task 4 的 chat）。
2. **checkpointer 不可用导致整个应用起不来**：数据库暂时连不上时，应用应当照常启动（降级为内存态）而不是崩溃（Task 2）。
3. **重启后历史消失**：这是本次要解决的根因，必须有跨进程重启的验证，而不是只测内存态（Task 10 端到端核验第 3 项）。
4. **首次提问没有索引行**：新会话的第一轮 chat 若忘了 upsert，会话列表里就永远看不到它（Task 4）。
5. **切回旧会话时历史错位**：历史消息的角色映射（human/ai）或工具调用丢失，会让用户看到「自己的话变成助手说的」（Task 3）。

---

## File Structure

**后端新增**
- `backend/alembic/versions/<rev>_ai_sessions.py` — 迁移
- `backend/tests/test_ai_sessions.py` — 会话索引与隔离
- `backend/tests/test_ai_history.py` — 历史消息读取

**后端修改**
- `backend/app/modules/ai/models.py`（`AiSession` 模型）
- `backend/app/modules/ai/repository.py`（**新建**：会话索引的数据访问；ai 模块原无 repository）
- `backend/app/modules/ai/service.py`（**新建**：会话业务门面：列表/删除/历史/upsert）
- `backend/app/modules/ai/api.py`（三个新端点 + `ChatIn.session_id`）
- `backend/app/modules/ai/schemas.py`（会话相关模式；若 ai 模块无此文件则新建）
- `backend/app/main.py`（lifespan 持有 checkpointer）
- `backend/agent/runner.py`（checkpointer 改为注入、`_extract_text` 供历史复用）
- `backend/app/models/__init__.py`（注册新模型）
- `backend/pyproject.toml`（+langgraph-checkpoint-postgres）

**前端修改**
- `frontend/src/layouts/AppLayout.vue`（删悬浮球、navItems 加「助理」）
- `frontend/src/components/AgentChat.vue`（session_id prop、历史加载、工具进行中态）
- `frontend/src/components/SessionList.vue`（**新建**）
- `frontend/src/pages/ChatPage.vue`（两栏布局）
- `frontend/src/api/ai.ts`（sessions API、`ChatIn.session_id`）
- `frontend/src/api/types.ts`（会话与历史消息类型）
- `frontend/tests/sessionList.spec.ts`（新建）

**文档**
- `TECH_DECISIONS.md`（D20）、`ARCHITECTURE.md`（表归属 + 接口地图）、`DESIGN.md`（助理页布局）

> **结构调整（相对 File Structure 段）**：ai 模块内部不用 `repository.py` / `service.py` 分层——既有的 `pending.py`、`semantic.py` 都是「一个功能一个文件，内含数据访问与业务」。会话这块跟随该风格，建 `app/modules/ai/sessions.py` 一个文件，不套三层。会话的 Pydantic 模式放 `api.py`（与其他 ai 模式一致，该模块无 `schemas.py`）。

---

## Phase 1：后端会话索引

### Task 1: ai_sessions 表与迁移

**Files:**
- Modify: `backend/app/modules/ai/models.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_ai_sessions.py`（autogenerate 产出）
- Test: `backend/tests/test_ai_sessions.py`

**Interfaces:**
- Produces: `AiSession` 模型（`session_id` PK / `user_id` / `title` / `created_at` / `updated_at`）

**设计取舍：** `session_id` 直接做主键（前端生成的 uuid，天然唯一），不加自增 id 列——用户 2026-09-27 确认。不带 D7 三件套：会话归属由 `user_id` 表达，隔离在 service 层校验（与 `pending_actions` 同类）。

- [ ] **Step 1: 加模型**

`backend/app/modules/ai/models.py` 末尾追加（`String` 若未导入则补进 sqlalchemy 导入行）：

```python
class AiSession(Base, TimestampMixin):
    """AI 会话索引：只承载列表展示与归属校验。

    对话内容本身由 LangGraph checkpointer 按 thread_id 存（D20），
    所以本表字段保持最小；thread_id 是 checkpointer 的实现细节，不入业务表。
    """

    __tablename__ = "ai_sessions"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="前端生成的会话标识（uuid）"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, comment="归属用户"
    )
    title: Mapped[str] = mapped_column(String(100), comment="取首条用户消息前若干字")
```

- [ ] **Step 2: 注册模型**

`backend/app/models/__init__.py` 的 ai 行改为：

```python
from app.modules.ai.models import AiSession, Embedding, PendingAction  # noqa: F401
```

- [ ] **Step 3: 写失败测试**

`backend/tests/test_ai_sessions.py`：

```python
"""AI 会话索引测试：表结构、归属隔离、列表与删除。"""

from sqlalchemy import text


async def test_ai_session_table_exists(db_session):
    """迁移后表存在且含约定列。"""
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ai_sessions'"
        )
    )
    columns = {row[0] for row in rows}

    assert {"session_id", "user_id", "title"} <= columns


async def test_session_id_is_primary_key(db_session):
    """session_id 是主键（前端生成的 uuid 天然唯一，不另加自增列）。"""
    rows = await db_session.execute(
        text(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = 'ai_sessions'::regclass AND i.indisprimary"
        )
    )
    primary_keys = {row[0] for row in rows}

    assert primary_keys == {"session_id"}
```

- [ ] **Step 4: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_sessions.py -v
```
预期：FAIL（表不存在 / 模型未注册）。

- [ ] **Step 5: 生成并清理迁移**

```bash
cd backend && uv run alembic revision --autogenerate -m "ai_sessions" && uv run alembic heads
```

打开生成的文件：**只保留 `ai_sessions` 的建表语句**，剔除 autogenerate 顺带产生的无关 alter_column / drop_constraint（本项目既有 schema 有已知漂移，上一次迁移也这样做过）。确认 `down_revision` 指向当前 head。

- [ ] **Step 6: 跑迁移与测试**

```bash
cd backend && uv run alembic upgrade head && uv run pytest tests/test_ai_sessions.py -v && uv run ruff check .
```
预期：迁移成功、2 passed。

- [ ] **Step 7: 提交**

```bash
git add backend/app/modules/ai/models.py backend/app/models/__init__.py backend/alembic/versions backend/tests/test_ai_sessions.py
git commit -m "feat(ai): ai_sessions 会话索引表"
```

---

### Task 2: checkpointer 换成持久化（含降级）

**Files:**
- Modify: `backend/pyproject.toml`（+langgraph-checkpoint-postgres）
- Modify: `backend/app/main.py`（lifespan 持有）
- Modify: `backend/agent/runner.py`（注入式 checkpointer）
- Test: `backend/tests/test_agent_runner.py`（追加）

**Interfaces:**
- Produces:
  - `runner.set_checkpointer(checkpointer)` — 由应用启动流程注入
  - `runner.get_checkpointer()` — 取当前实例；未注入时退回进程内内存（测试与降级路径）
  - `main._open_checkpointer()` — async context manager，产出 checkpointer（失败则降级为 `InMemorySaver`）

**为什么必须注入而不是模块级单例：** `AsyncPostgresSaver.from_conn_string()` 是 async context manager，连接要在进程生命周期内长期持有；而测试不跑 lifespan，需要退回内存态。两者用「可注入的模块级变量」同时满足。

- [ ] **Step 1: 加依赖**

```bash
cd backend && uv add langgraph-checkpoint-postgres
```
预期：`pyproject.toml` 出现该依赖，`uv.lock` 更新（会带入 `psycopg` + `psycopg-pool`）。

- [ ] **Step 2: 写失败测试**

追加到 `backend/tests/test_agent_runner.py`：

```python
async def test_checkpointer_defaults_to_in_memory():
    """未注入时退回进程内内存：测试与降级路径都依赖这一点。"""
    import agent.runner as runner

    runner._CHECKPOINTER = None
    checkpointer = runner.get_checkpointer()

    assert checkpointer is not None
    assert type(checkpointer).__name__ == "InMemorySaver"


async def test_set_checkpointer_overrides_default():
    """注入后 get_checkpointer 返回注入的实例（生产走这条）。"""
    import agent.runner as runner
    from langgraph.checkpoint.memory import InMemorySaver

    injected = InMemorySaver()
    runner.set_checkpointer(injected)

    try:
        assert runner.get_checkpointer() is injected
    finally:
        runner._CHECKPOINTER = None


async def test_checkpointer_open_falls_back_when_unavailable(monkeypatch):
    """checkpointer 建立失败不应让应用起不来——降级为内存态。"""
    from app import main

    def _explode(*args, **kwargs):
        raise OSError("数据库连不上")

    monkeypatch.setattr(
        "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver.from_conn_string", _explode
    )

    async with main._open_checkpointer() as checkpointer:
        assert type(checkpointer).__name__ == "InMemorySaver"
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_agent_runner.py -k "checkpointer" -v
```
预期：FAIL（`get_checkpointer` / `set_checkpointer` / `_open_checkpointer` 不存在）。

- [ ] **Step 4: 改 runner.py**

把模块级 `_CHECKPOINTER = InMemorySaver()` 替换为可注入变量与两个访问函数：

```python
# 会话记忆的 checkpointer：由应用启动流程注入（见 app/main.py 的 lifespan）。
# 未注入时退回进程内内存——测试不跑 lifespan，降级路径也走这里。
_CHECKPOINTER: BaseCheckpointSaver | None = None


def set_checkpointer(checkpointer: BaseCheckpointSaver) -> None:
    """注入会话持久化 checkpointer（应用启动时调用一次）。"""
    global _CHECKPOINTER
    _CHECKPOINTER = checkpointer


def get_checkpointer() -> BaseCheckpointSaver:
    """取当前 checkpointer；尚未注入时懒建一个进程内内存实例。"""
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        _CHECKPOINTER = InMemorySaver()
    return _CHECKPOINTER
```

`stream_agent` 里 `checkpointer=_CHECKPOINTER` 改为 `checkpointer=get_checkpointer()`，并补导入：

```python
from langgraph.checkpoint.base import BaseCheckpointSaver
```

**`thread_id` 的拼装仍留在本文件**（业务侧只认 session_id）：

```python
    config = {"configurable": {"thread_id": f"{user.id}:{session_id}"}}
```
（参数名从 `thread_id` 改为 `session_id`，函数签名同步改。）

- [ ] **Step 5: 改 main.py 的 lifespan**

在 `app/main.py` 模块级加一个 context manager（放在 `create_app` 之前）：

```python
@asynccontextmanager
async def _open_checkpointer():
    """打开会话持久化 checkpointer；不可用时降级为内存态，不阻断应用启动。

    AsyncPostgresSaver 依赖 psycopg3（与业务用的 asyncpg 并存），
    连接串从既有的 DATABASE_URL 去掉方言前缀派生，不新增配置项。
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    dsn = get_settings().database_url.replace("+asyncpg", "")
    try:
        async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
            await checkpointer.setup()  # 官方要求：首次使用必须建表
            logger.info("会话持久化已启用（PostgreSQL checkpointer）")
            yield checkpointer
    except Exception as exc:  # 数据库暂时不可用不该让整个应用起不来
        logger.warning("会话持久化不可用，降级为内存态：%s", exc)
        yield InMemorySaver()
```

lifespan 改为在外层持有它：

```python
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """宿主生命周期：清理临时文件 + 持有会话 checkpointer + MCP 会话管理器。"""
        from agent.runner import set_checkpointer
        from app.modules.ai.mcp_endpoint import mcp_lifespan
        from app.services import storage

        removed = storage.cleanup_temp()
        if removed:
            logger.info("启动清理：删除 %d 个过期临时文件", removed)

        async with _open_checkpointer() as checkpointer:
            set_checkpointer(checkpointer)
            async with mcp_lifespan():
                yield
```

- [ ] **Step 6: 跑测试**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```
预期：新用例 PASS，既有 178 个测试仍全绿（测试不跑 lifespan，走内存态）。

- [ ] **Step 7: 提交**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/main.py backend/agent/runner.py backend/tests/test_agent_runner.py
git commit -m "feat(ai): 会话记忆换成持久化 checkpointer（D20）"
```

---

### Task 3: 历史消息读取

**Files:**
- Modify: `backend/agent/runner.py`（加 `load_history`）
- Modify: `backend/app/modules/ai/sessions.py`（**新建**）
- Modify: `backend/app/modules/ai/api.py`（`GET /ai/sessions/{session_id}/messages`）
- Test: `backend/tests/test_ai_history.py`

**Interfaces:**
- Consumes: `runner.get_checkpointer()`（Task 2）
- Produces:
  - `runner.load_history(session_id: str, user_id: int) -> list[dict]` — 归一为 `[{role, content, tools}]`
  - `sessions.get_history(db, user, session_id) -> list[dict]` — 归属校验后转发
  - `GET /api/v1/ai/sessions/{session_id}/messages` → `list[HistoryMessageOut]`

**为什么归一放在 runner：** LangChain 的消息对象形状是 agent 层的实现细节，业务层只该看到 `{role, content, tools}`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_ai_history.py`：

```python
"""历史消息读取测试：角色映射、工具提取、归属隔离。"""

import pytest


async def test_load_history_maps_roles_and_skips_tool_messages(checkpointer):
    """human→user、ai→assistant；工具消息不进历史（调用已记在 ai 消息上）。"""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from agent.runner import load_history

    await _write_thread(
        checkpointer,
        "1:s1",
        [HumanMessage("老爸最近怎么样"), AIMessage("我查一下"), ToolMessage("ok", tool_call_id="t1")],
    )

    history = await load_history("s1", user_id=1)

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "老爸最近怎么样"


async def test_load_history_extracts_tool_calls():
    """AI 消息里发起的工具调用要出现在该条的 tools 上（前端据此渲染 tag）。"""
    from langchain_core.messages import AIMessage, HumanMessage

    from agent.runner import load_history

    await _write_thread(
        checkpointer,
        "1:s2",
        [
            HumanMessage("帮我查统计"),
            AIMessage("", tool_calls=[{"name": "get_stats", "args": {}, "id": "t1"}]),
        ],
    )

    history = await load_history("s2", user_id=1)

    assert history[1]["tools"] == ["get_stats"]


async def test_load_history_unknown_session_is_empty(checkpointer):
    """还没有任何 checkpoint 的会话返回空列表（不是报错）。"""
    from agent.runner import load_history

    assert await load_history("never-existed", user_id=1) == []


async def test_session_messages_requires_ownership(client, login_headers, make_user, db_session):
    """读别人会话的历史必须 404——越权读是红线（Review Focus #1）。"""
    from app.modules.ai.models import AiSession

    owner, _ = await make_user(username="hist_owner", password="pw12345678")
    await make_user(username="hist_other", password="pw12345678")
    headers = await login_headers("hist_other", "pw12345678")
    db_session.add(AiSession(session_id="owned-hist", user_id=owner.id, title="他的对话"))
    await db_session.commit()

    response = await client.get("/api/v1/ai/sessions/owned-hist/messages", headers=headers)

    assert response.status_code == 404
```

同文件里加写 checkpoint 的助手（`aput` 的 checkpoint 结构照官方 README 示例）：

```python
async def _write_thread(checkpointer, thread_id: str, messages: list) -> None:
    """把一批消息写成一个 checkpoint，供历史读取测试使用。"""
    checkpoint = {
        "v": 4,
        "id": "1ef4f797-8335-6428-8001-8a1503f9b875",
        "ts": "2026-09-27T20:14:19.804150+00:00",
        "channel_values": {"messages": messages},
        "channel_versions": {"__start__": 2, "messages": 3},
        "versions_seen": {"__input__": {}, "__start__": {"__start__": 1}},
    }
    config = {"configurable": {"thread_id": thread_id}}
    await checkpointer.aput(config, checkpoint, {"source": "input", "step": 0, "parents": {}}, {})
```

并在 `backend/tests/conftest.py` 加一个 fixture（历史读取需要真 checkpointer，用内存态即可，与生产实现共用同一套读写接口）：

```python
@pytest.fixture
async def checkpointer(monkeypatch):
    """把 runner 的 checkpointer 指到一个测试专用的内存实例。"""
    import agent.runner as runner
    from langgraph.checkpoint.memory import InMemorySaver

    instance = InMemorySaver()
    runner.set_checkpointer(instance)
    yield instance
    runner._CHECKPOINTER = None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_history.py -v
```
预期：FAIL（`load_history` 不存在）。

- [ ] **Step 3: 实现 load_history**

`backend/agent/runner.py` 追加：

```python
def _to_history_messages(messages) -> list[dict]:
    """把 LangChain 消息归一为前端可渲染的形状。

    工具消息（ToolMessage）不进历史——它的调用已经记在发起它的 AI 消息的
    tool_calls 上，单独列出来只会让用户看到一条没有上下文的噪音。
    """
    items: list[dict] = []
    for message in messages or []:
        role = {"human": "user", "ai": "assistant"}.get(getattr(message, "type", ""))
        if role is None:
            continue
        items.append(
            {
                "role": role,
                "content": _extract_text(getattr(message, "content", None)),
                "tools": [
                    call.get("name")
                    for call in getattr(message, "tool_calls", None) or []
                    if call.get("name")
                ],
            }
        )
    return items


async def load_history(session_id: str, user_id: int) -> list[dict]:
    """读取某会话的历史消息（归一形状）。

    thread_id 的拼装只在这里发生：业务侧永远只认 session_id。
    """
    checkpointer = get_checkpointer()
    config = {"configurable": {"thread_id": f"{user_id}:{session_id}"}}
    snapshot = await checkpointer.aget_tuple(config)
    if snapshot is None:
        return []
    return _to_history_messages(snapshot.checkpoint.get("channel_values", {}).get("messages"))
```

- [ ] **Step 4: service 与端点**

`backend/app/modules/ai/sessions.py`（新建）：

```python
"""ai 模块的会话索引与会话业务：列表、删除、历史、首轮 upsert。

与 ai 模块其他文件一致（pending.py / semantic.py）：一个功能一个文件，
内含数据访问与业务，不套 repository/service 三层。
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.ai.models import AiSession
from app.modules.auth.models import User

# 会话标题长度：够在列表里认出是哪次对话即可
TITLE_LIMIT = 30


def make_title(message: str) -> str:
    """取首条用户消息的前若干字作为会话标题（压掉换行，避免列表被撑开）。"""
    return " ".join(message.split())[:TITLE_LIMIT] or "新对话"
```

接着写数据访问与业务（**归属校验是这里的唯一职责边界**）：

```python
async def list_sessions(db: AsyncSession, user: User) -> list[AiSession]:
    """列出当前用户的会话，按最后活跃倒序。"""
    stmt = (
        select(AiSession)
        .where(AiSession.user_id == user.id)
        .order_by(AiSession.updated_at.desc(), AiSession.session_id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_owned_session(db: AsyncSession, user: User, session_id: str) -> AiSession:
    """取当前用户拥有的会话；不存在或不属于本人一律 404（不泄露存在性）。"""
    stmt = select(AiSession).where(
        AiSession.session_id == session_id, AiSession.user_id == user.id
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None:
        raise NotFoundError("会话不存在")
    return session


async def ensure_session(db: AsyncSession, user: User, session_id: str, first_message: str) -> None:
    """首轮提问时建立会话索引行（已存在则不动，只更新活跃时间）。

    没有单独的「创建会话」端点——少一个接口、少一次往返。
    """
    existing = await db.get(AiSession, session_id)
    if existing is not None:
        if existing.user_id != user.id:
            # 主键撞车说明前端生成的 id 不属于本人：按不可用处理，不泄露他人会话
            raise NotFoundError("会话不存在")
        existing.updated_at = func.now()
        return
    db.add(AiSession(session_id=session_id, user_id=user.id, title=make_title(first_message)))


async def delete_session(db: AsyncSession, user: User, session_id: str) -> None:
    """删除会话索引行（对话内容由调用方经 checkpointer 清）。"""
    session = await get_owned_session(db, user, session_id)
    await db.delete(session)


async def get_history(db: AsyncSession, user: User, session_id: str) -> list[dict]:
    """读取会话历史：先校验归属，再取 checkpointer 里的消息。"""
    from agent.runner import load_history

    await get_owned_session(db, user, session_id)
    return await load_history(session_id, user.id)
```

`updated_at = func.now()` 需要 `from sqlalchemy import func`。`delete` 未用到则去掉该导入。

`backend/app/modules/ai/api.py` 追加端点与模式：

```python
class AiSessionOut(BaseModel):
    """会话索引输出。"""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class HistoryMessageOut(BaseModel):
    """历史消息：与流式事件的渲染形状一致，前端可复用同一套渲染。"""

    role: str
    content: str
    tools: list[str] = []


@router.get("/sessions", response_model=list[AiSessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AiSessionOut]:
    """我的会话列表（按最后活跃倒序）。"""
    return await sessions.list_sessions(db, current_user)


@router.get("/sessions/{session_id}/messages", response_model=list[HistoryMessageOut])
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HistoryMessageOut]:
    """某会话的历史消息；不属于当前用户按 404 处理。"""
    return await sessions.get_history(db, current_user, session_id)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除会话：索引行与 checkpointer 数据一并清掉。"""
    from agent.runner import delete_history

    await sessions.get_owned_session(db, current_user, session_id)
    await delete_history(session_id, current_user.id)
    await sessions.delete_session(db, current_user, session_id)
    return Response(status_code=204)
```

`runner.py` 补 `delete_history`：

```python
async def delete_history(session_id: str, user_id: int) -> None:
    """删除某会话在 checkpointer 里的全部数据（线程级清理）。"""
    checkpointer = get_checkpointer()
    await checkpointer.adelete_thread(f"{user_id}:{session_id}")
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd backend && uv run pytest tests/test_ai_history.py -v && uv run ruff check .
```
预期：PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/agent/runner.py backend/app/modules/ai backend/tests/test_ai_history.py backend/tests/conftest.py
git commit -m "feat(ai): 会话历史读取与删除"
```

---

### Task 4: chat 端点接入 session_id

**Files:**
- Modify: `backend/app/modules/ai/api.py`（`ChatIn` 字段改名 + upsert）
- Test: `backend/tests/test_ai_chat.py`（追加）

**Interfaces:**
- Consumes: `sessions.ensure_session`（Task 3）、`runner.stream_agent`（Task 2 改了签名）
- Produces: `POST /ai/chat` 的请求体字段 `session_id: str`（**破坏性变更**：原 `thread_id` 不再接受）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_chat.py`（沿用该文件已有的 `fake_stream` 打桩方式）：

```python
async def test_chat_creates_session_index_on_first_turn(client, login_headers, make_user):
    """首轮提问要顺手建立会话索引行，否则会话列表里永远看不到它（Review Focus #4）。"""
    from app.modules.ai.models import AiSession

    user, _ = await make_user(username="chat_owner", password="pw12345678")
    headers = await login_headers("chat_owner", "pw12345678")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "老爸最近怎么样", "session_id": "sess-first"},
        headers=headers,
    )

    assert response.status_code == 200
    factory = get_session_factory()
    async with factory() as session:
        stored = await session.get(AiSession, "sess-first")
    assert stored is not None
    assert stored.user_id == user.id
    assert stored.title == "老爸最近怎么样"


async def test_chat_rejects_session_id_owned_by_other_user(client, login_headers, make_user):
    """拿到别人的 session_id 提问必须被拒（Review Focus #1）。"""
    await make_user(username="sess_owner", password="pw12345678")
    await make_user(username="sess_intruder", password="pw12345678")
    owner_headers = await login_headers("sess_owner", "pw12345678")
    intruder_headers = await login_headers("sess_intruder", "pw12345678")
    await client.post(
        "/api/v1/ai/chat",
        json={"message": "我的私事", "session_id": "sess-owned"},
        headers=owner_headers,
    )

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "偷看", "session_id": "sess-owned"},
        headers=intruder_headers,
    )

    assert "会话不存在" in response.text
```

`get_session_factory` 需从 `app.core.db` 导入。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run pytest tests/test_ai_chat.py -k "session" -v
```
预期：FAIL（`session_id` 字段不存在 → 422，或索引行未建）。

- [ ] **Step 3: 实现**

`api.py` 的 `ChatIn`：

```python
class ChatIn(BaseModel):
    """对话请求：session_id 由前端生成（一个对话一个 id），缺失则服务端补一个。"""

    message: str
    session_id: str | None = None
```

`chat` 端点的 `event_stream` 改为（在 `start` 帧之前 upsert）：

```python
    async def event_stream():
        session_id = body.session_id or str(uuid.uuid4())
        try:
            # 首轮提问顺手建索引行；已存在则只更新活跃时间。
            # 主键撞车（属于他人）会抛 NotFoundError，一并走下面的错误帧。
            await sessions.ensure_session(db, current_user, session_id, body.message)
            yield _sse({"type": "start", "session_id": session_id})
            llm = await require_llm(db)
            from agent.runner import stream_agent

            async for event in stream_agent(db, current_user, llm, body.message, session_id):
                yield _sse(event)
        except LLMNotConfiguredError as exc:
            yield _sse({"type": "error", "code": "llm_not_configured", "message": exc.message})
        except BusinessError as exc:
            yield _sse({"type": "error", "message": exc.message})
        yield _sse({"type": "done"})
```

**注意 SSE 的语义**：`ensure_session` 的失败也要走 error 帧（客户端已在读流），不能在流开始前抛 HTTP 异常——否则前端拿到的是连接错误而不是可读提示。

- [ ] **Step 4: 跑全量测试**

```bash
cd backend && uv run pytest -q && uv run ruff check .
```
预期：新用例 PASS；既有 chat 测试若用到 `thread_id` 字段需同步改名（属预期的契约变更）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/modules/ai/api.py backend/tests/test_ai_chat.py
git commit -m "feat(ai): chat 接入 session_id 并建立会话索引"
```

---

## Phase 2：前端

### Task 5: 去掉悬浮球、导航加入口

**Files:**
- Modify: `frontend/src/layouts/AppLayout.vue`

**Interfaces:**
- Produces: 导航第 2 项「助理」→ `/assistant`；`AppLayout` 不再引用 `AgentChat`

- [ ] **Step 1: 改导航**

`navItems` 在主页之后插入：

```ts
const navItems = [
  { key: 'home', label: '主页', icon: HomeOutline, to: '/home' },
  { key: 'assistant', label: '助理', icon: Sparkles, to: '/assistant' },
  { key: 'contacts', label: '名册', icon: PeopleOutline, to: '/contacts' },
  // ...其余不变
]
```

`Sparkles` 已在文件内导入（悬浮球用过），保留该导入。

- [ ] **Step 2: 删悬浮球**

删掉：`import AgentChat from '@/components/AgentChat.vue'`、`const chatOpen = ref(false)`、模板里的 `<button class="ai-fab">` 与 `<transition name="fab-pop">…<AgentChat compact /></transition>` 整块、以及样式里的 `.ai-fab` / `.fab-icon` / `.ai-float` / `.ai-float-head` / `.ai-float-title` / `.fab-pop-*` 与窄屏下针对它们的媒体查询。`compact` prop 随之成为死参数（Task 8 一并删）。

- [ ] **Step 3: 验证**

```bash
cd frontend && npm run build && npm run test
```
浏览器核验（开发环境）：任意页面**不再有**右下角悬浮球；侧边栏「主页」下面出现「助理」，点击进入 `/assistant`；窄屏菜单里同样有该入口。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/layouts/AppLayout.vue
git commit -m "feat(layout): 助理提升为导航独立入口，移除 AI 悬浮球"
```

---

### Task 6: 前端 API 层与类型

**Files:**
- Modify: `frontend/src/api/ai.ts`、`frontend/src/api/types.ts`

**Interfaces:**
- Produces:
  - `aiApi.sessions()` → `AiSessionOut[]`
  - `aiApi.sessionMessages(sessionId)` → `HistoryMessageOut[]`
  - `aiApi.removeSession(sessionId)` → `void`
  - `aiApi.chat(message, sessionId, onEvent)`（参数由 `threadId` 改名）
  - 类型：`AiSessionOut`、`HistoryMessageOut`；`ChatStreamEvent.session_id` 取代 `thread_id`

- [ ] **Step 1: 改类型与 API**

`types.ts` 追加：

```ts
/** AI 会话索引（列表展示用） */
export interface AiSessionOut {
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

/** 历史消息：与流式渲染同形状，前端复用同一套渲染 */
export interface HistoryMessageOut {
  role: 'user' | 'assistant'
  content: string
  tools: string[]
}
```

`ai.ts` 的 `ChatStreamEvent` 把 `thread_id` 改为 `session_id`，并加三个方法：

```ts
  /** 我的会话列表（按最后活跃倒序）。 */
  sessions: () => api.get<AiSessionOut[]>('/ai/sessions'),
  /** 某会话的历史消息（切换会话时用）。 */
  sessionMessages: (sessionId: string) =>
    api.get<HistoryMessageOut[]>(`/ai/sessions/${sessionId}/messages`),
  /** 删除会话（索引与对话内容一并清）。 */
  removeSession: (sessionId: string) => api.delete<void>(`/ai/sessions/${sessionId}`),
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npm run build
```
预期：会有**预期内的报错**——`AgentChat.vue` 仍在用 `threadId`。Task 8 修。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/ai.ts frontend/src/api/types.ts
git commit -m "feat(api): 会话列表、历史消息与 session_id 契约"
```

---

### Task 7: SessionList 组件

**Files:**
- Create: `frontend/src/components/SessionList.vue`
- Create: `frontend/tests/sessionList.spec.ts`

**Interfaces:**
- Props: `sessions: AiSessionOut[]`、`activeId: string | null`
- Emits: `select: [sessionId: string]`、`create: []`、`remove: [sessionId: string]`

- [ ] **Step 1: 写失败测试**

`frontend/tests/sessionList.spec.ts`：

```ts
/** 会话列表交互测试。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import SessionList from '@/components/SessionList.vue'
import type { AiSessionOut } from '@/api/types'

/** 该组件用到 el-button / el-popconfirm，挂载时必须注册组件库，否则渲染不出来。 */
const MOUNT_OPTIONS = { global: { plugins: [ElementPlus] } }

const SESSIONS: AiSessionOut[] = [
  { session_id: 'a', title: '老爸最近怎么样', created_at: '2026-09-27T10:00:00Z', updated_at: '2026-09-27T12:00:00Z' },
  { session_id: 'b', title: '记一笔待办', created_at: '2026-09-26T10:00:00Z', updated_at: '2026-09-26T10:00:00Z' },
]

describe('SessionList', () => {
  it('渲染会话标题', () => {
    const wrapper = mount(SessionList, { props: { sessions: SESSIONS, activeId: null }, ...MOUNT_OPTIONS })

    expect(wrapper.text()).toContain('老爸最近怎么样')
    expect(wrapper.text()).toContain('记一笔待办')
  })

  it('点某条会话抛出 select 事件', async () => {
    const wrapper = mount(SessionList, { props: { sessions: SESSIONS, activeId: null }, ...MOUNT_OPTIONS })

    await wrapper.findAll('[data-test="session-item"]')[1].trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual(['b'])
  })

  it('当前会话有选中态', () => {
    const wrapper = mount(SessionList, { props: { sessions: SESSIONS, activeId: 'a' }, ...MOUNT_OPTIONS })

    expect(wrapper.findAll('[data-test="session-item"]')[0].classes()).toContain('active')
    expect(wrapper.findAll('[data-test="session-item"]')[1].classes()).not.toContain('active')
  })

  it('点新建抛出 create 事件', async () => {
    const wrapper = mount(SessionList, { props: { sessions: [], activeId: null }, ...MOUNT_OPTIONS })

    await wrapper.find('[data-test="new-session"]').trigger('click')

    expect(wrapper.emitted('create')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run tests/sessionList.spec.ts
```
预期：FAIL（组件不存在）。

- [ ] **Step 3: 实现**

```vue
<script setup lang="ts">
/** 会话列表：新建 / 切换 / 删除。数据和动作都由父页面持有，本组件只负责展示与抛出意图。 */
import type { AiSessionOut } from '@/api/types'

defineProps<{ sessions: AiSessionOut[]; activeId: string | null }>()
const emit = defineEmits<{
  select: [sessionId: string]
  create: []
  remove: [sessionId: string]
}>()

/** 列表里的时间只到「日」：会话列表用于认出是哪次对话，精确到分没有意义。 */
function formatDay(value: string): string {
  return new Date(value).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}
</script>

<template>
  <aside class="session-list">
    <el-button class="new" type="primary" plain @click="emit('create')" data-test="new-session">
      新对话
    </el-button>
    <ul class="items">
      <li
        v-for="session in sessions"
        :key="session.session_id"
        class="item"
        :class="{ active: session.session_id === activeId }"
        data-test="session-item"
        @click="emit('select', session.session_id)"
      >
        <span class="title">{{ session.title }}</span>
        <span class="day">{{ formatDay(session.updated_at) }}</span>
        <el-popconfirm
          title="删除这个对话？"
          confirm-button-text="删除"
          cancel-button-text="取消"
          @confirm="emit('remove', session.session_id)"
        >
          <template #reference>
            <el-button text size="small" type="danger" @click.stop>删除</el-button>
          </template>
        </el-popconfirm>
      </li>
    </ul>
    <p v-if="!sessions.length" class="empty">还没有对话</p>
  </aside>
</template>

<style scoped>
.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.new {
  width: 100%;
}
.items {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 6px 8px;
  border-radius: var(--crm-radius-control);
  border-bottom: 1px solid var(--crm-line);
  cursor: pointer;
  transition: background var(--crm-ease);
}
.item:hover {
  background: var(--crm-bone);
}
.item.active {
  background: var(--crm-bone);
}
.title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.day {
  color: var(--crm-muted);
  font-size: 12px;
  flex-shrink: 0;
}
.empty {
  margin: 12px 0;
  color: var(--crm-muted);
  font-size: 13px;
  text-align: center;
}
</style>
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && npx vitest run tests/sessionList.spec.ts && npm run build
```
预期：4 passed。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/SessionList.vue frontend/tests/sessionList.spec.ts
git commit -m "feat(frontend): 会话列表组件"
```

---

### Task 8: AgentChat 适配 session 与历史

**Files:**
- Modify: `frontend/src/components/AgentChat.vue`

**Interfaces:**
- Props: `sessionId: string`（取代原 `compact?: boolean`；sessionId 由页面持有）
- Emits: `updated: []`（一轮对话结束后通知父页面刷新会话列表）

**改动要点（本组件已具备流式与工具 tag 渲染，本次只做适配与补强）：**

1. `defineProps<{ compact?: boolean }>()` → `defineProps<{ sessionId: string }>()`；删掉所有 `compact` 分支与紧凑样式。
2. 删内部 `threadId` ref；发送时用 `props.sessionId`，`start` 帧的 `session_id` 不再需要写回（前端已经是权威来源）。
3. **切换会话要重新载入历史**：`watch(() => props.sessionId, loadHistory, { immediate: true })`。
4. **工具调用进行中态**：新增 `activeTool` ref，收到 `tool` 事件时置为该工具名，收到 `text` 事件时清空，气泡上方显示「正在调用 X…」。

- [ ] **Step 1: 实现**

替换 script 中的状态与发送逻辑（保留既有的消息渲染、写入提议面板、错误处理）：

```ts
const props = defineProps<{ sessionId: string }>()
const emit = defineEmits<{ updated: [] }>()

const messages = ref<ChatMessage[]>([])
const streaming = ref(false)
/** 正在进行中的工具调用名；收到文本增量即视为该工具已返回。 */
const activeTool = ref<string | null>(null)

/** 载入该会话的历史消息（切换会话时调用；空会话得到空列表）。 */
async function loadHistory(): Promise<void> {
  messages.value = []
  activeTool.value = null
  if (!props.sessionId) return
  try {
    const history = await aiApi.sessionMessages(props.sessionId)
    messages.value = history.map((item) => ({
      role: item.role,
      content: item.content,
      tools: item.tools,
    }))
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('历史消息加载失败')
  }
}

watch(() => props.sessionId, loadHistory, { immediate: true })
```

发送改为使用 props 上的 id，并在结束后通知父页面：

```ts
async function send(): Promise<void> {
  const text = input.value.trim()
  if (!text || streaming.value) return
  messages.value.push({ role: 'user', content: text, tools: [] })
  const reply: ChatMessage = { role: 'assistant', content: '', tools: [] }
  messages.value.push(reply)
  input.value = ''
  streaming.value = true
  activeTool.value = null
  try {
    await aiApi.chat(text, props.sessionId, (event) => handleEvent(event, reply))
  } catch {
    reply.content = reply.content || '连接中断，请重试'
  } finally {
    streaming.value = false
    activeTool.value = null
    emit('updated')  // 首轮会产生会话索引行，让父页面刷新列表
  }
}

/** 事件分流：文本增量累积、工具调用进入进行中态。 */
function handleEvent(event: ChatStreamEvent, reply: ChatMessage): void {
  if (event.type === 'text' && event.delta) {
    reply.content += event.delta
    activeTool.value = null
    return
  }
  if (event.type === 'tool' && event.name) {
    activeTool.value = event.name
    if (!reply.tools.includes(event.name)) reply.tools.push(event.name)
    return
  }
  if (event.type === 'error' && event.message) {
    ElMessage.error(event.message)
  }
}
```

模板在消息区顶部加进行中提示（放在消息列表之后、输入区之前）：

```vue
      <div v-if="activeTool" class="tool-running">
        <el-tag size="small" type="info">正在调用 {{ activeTool }}…</el-tag>
      </div>
```

样式加：

```css
.tool-running {
  padding: 4px 0;
}
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npm run build && npm run test
```
浏览器核验：提问时能看到「正在调用 get_stats…」出现又消失；工具 tag 落在该条回复上；答复逐字出现（流式未回归）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/AgentChat.vue
git commit -m "feat(ai): 对话组件适配 session 与历史载入，补工具进行中态"
```

---

### Task 9: ChatPage 改两栏

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`

**Interfaces:**
- Consumes: `SessionList`（Task 7）、`AgentChat`（Task 8）、`aiApi.sessions/sessionMessages/removeSession`（Task 6）

- [ ] **Step 1: 实现**

```vue
<script setup lang="ts">
/** 助理页：左侧会话列表 + 右侧对话区。
 *
 * session_id 由前端生成（crypto.randomUUID）——后端按它持久化，见 D20。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi } from '@/api/ai'
import { ApiError } from '@/api/client'
import AgentChat from '@/components/AgentChat.vue'
import SessionList from '@/components/SessionList.vue'
import type { AiSessionOut } from '@/api/types'

const sessions = ref<AiSessionOut[]>([])
const activeSessionId = ref<string>('')

/** 刷新会话列表（按最后活跃倒序，后端已排序）。 */
async function loadSessions(): Promise<void> {
  try {
    sessions.value = await aiApi.sessions()
    // 空列表（首次使用）或当前会话已被删：开一个新对话
    if (!sessions.value.some((item) => item.session_id === activeSessionId.value)) {
      activeSessionId.value = sessions.value[0]?.session_id ?? newSessionId()
    }
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('会话列表加载失败')
  }
}

/** 生成新会话标识（前端是权威来源，后端不生成）。 */
function newSessionId(): string {
  return crypto.randomUUID()
}

/** 开一个新对话（此时还没有索引行，首轮提问后才会出现在列表里）。 */
function createSession(): void {
  activeSessionId.value = newSessionId()
}

/** 删除会话并切到下一个（没有剩余则开新对话）。 */
async function removeSession(sessionId: string): Promise<void> {
  try {
    await aiApi.removeSession(sessionId)
    ElMessage.success('对话已删除')
    if (sessionId === activeSessionId.value) activeSessionId.value = ''
    await loadSessions()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

onMounted(loadSessions)
</script>

<template>
  <div class="crm-page assistant-page">
    <header class="page-head">
      <div>
        <h1 class="page-title crm-display">助 手</h1>
        <p class="page-sub">自然语言查名册、记待办、记活动；写入需你确认后生效</p>
      </div>
      <a class="crm-link" href="/settings">LLM 设置</a>
    </header>
    <div class="chat-layout">
      <SessionList
        :sessions="sessions"
        :active-id="activeSessionId"
        @select="activeSessionId = $event"
        @create="createSession"
        @remove="removeSession"
      />
      <div class="chat-card">
        <AgentChat :session-id="activeSessionId" @updated="loadSessions" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.assistant-page {
  height: calc(100vh - 88px);
  display: flex;
  flex-direction: column;
}
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  margin: 0;
  font-size: 32px;
}
.page-sub {
  margin: 8px 0 0;
  color: var(--crm-muted);
  font-size: 14px;
}
/* 两栏：会话列表定宽、对话区自适应 */
.chat-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
}
.chat-card {
  min-height: 0;
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
  overflow: hidden;
}
/* 窄屏退化为上下排列（列表在上） */
@media (max-width: 720px) {
  .chat-layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
}
</style>
```

- [ ] **Step 2: 核验**

浏览器逐项验证：新建对话 → 首轮提问后左侧列表出现该会话（标题是提问前 30 字）→ 切到另一个会话再切回来，**历史消息还在**（这是本次的核心价值）→ 删除会话，列表与内容同步清掉。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat(ai): 助理页改两栏（会话列表 + 对话区）"
```

---

## Phase 3：文档与收尾

### Task 10: 文档登记与全量验证

**Files:**
- Modify: `TECH_DECISIONS.md`、`ARCHITECTURE.md`、`DESIGN.md`

- [ ] **Step 1: TECH_DECISIONS.md**

决策总览表追加一行，并在文件末尾（D19 之后）加小节：

```markdown
| D20 | **助理会话持久化**：session（业务）/ thread（LangGraph）分层命名；`ai_sessions` 索引表 + `AsyncPostgresSaver`；session_id 前端生成 | ✅ | 2026-09-27 |
```

小节要点：背景（原 `InMemorySaver` 重启即丢历史）；决策（① 命名分层：业务只认 `session_id`，`thread_id` 仅存在于 `runner.py`；② 索引表 `ai_sessions`，`session_id` 直接做主键，只承载列表/标题/活跃时间；③ checkpointer 换 `AsyncPostgresSaver`，lifespan 长期持有、失败降级内存态；④ 连接串从 `DATABASE_URL` 派生，不新增配置；⑤ 首轮 chat 顺手 upsert 索引行，无独立创建端点）；理由；影响（**引入第二个数据库驱动 psycopg3**，与 asyncpg 并存，前者只服务 checkpointer）。

- [ ] **Step 2: ARCHITECTURE.md**

- 第 3 节表归属加 `| ai_sessions | ai | users（user_id） |`。
- 第 4 节 `/api/v1/ai` 行补 `GET|DELETE /ai/sessions`、`GET /ai/sessions/{id}/messages`，并把「SSE 对话」的请求字段说明为 `session_id`。
- 第 1 节 ai 模块职责描述补一句：会话索引与会话业务在 `modules/ai/sessions.py`。

- [ ] **Step 3: DESIGN.md**

「图片与往来时间线」一节后补「助理页（2026-09-27）」：两栏栅格 `220px + 1fr`、栅格间距 16px；会话列表项 44px 高、悬停/选中同为 `--crm-bone` 底、标题单行省略；窄屏 <720px 退化为上下排列；**移除**任何关于 AI 悬浮球的描述（若有）。

- [ ] **Step 4: 全量验证**

```bash
cd backend && uv run pytest -q && uv run ruff check .
cd ../frontend && npm run test && npm run build
```

- [ ] **Step 5: 端到端核验（重启后端让新代码生效）**

`dev.sh` 起的 uvicorn 无 `--reload`，必须先重启：

```bash
lsof -ti :8100 | xargs kill; sleep 2
cd backend && nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8100 > /tmp/crm-backend.log 2>&1 &
```

启动日志里应出现「会话持久化已启用（PostgreSQL checkpointer）」。

逐项核验：
1. 导航「主页」下面是「助理」，页面无悬浮球。
2. 提问 → 答复逐字出现；能看到「正在调用 X…」。
3. **重启后端进程**后再进助理页 → 旧会话与历史**仍在**（这是本次的核心验收点，内存态时必丢）。
4. 用另一个账号登录 → 看不到前一个账号的会话（跨用户隔离）。
5. 删除会话 → 列表消失，重新进入不再出现。

- [ ] **Step 6: 提交**

```bash
git add TECH_DECISIONS.md ARCHITECTURE.md DESIGN.md
git commit -m "docs: 登记 D20 与助理页布局"
```
