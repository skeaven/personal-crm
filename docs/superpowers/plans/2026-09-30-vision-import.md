# 视觉导入（对话框传图 → 识别 → 确认落库）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 助理对话框支持上传一张图片，用与 agent 相同的 LLM 识别内容并生成「建联系人」写入提议，经既有确认队列落库；模型不支持视觉时给出专属报错。

**Architecture:** 图片经既有 `POST /uploads/temp` 进本人临时区；`/ai/chat` 契约加 `images`（端点校验后转 data URI）；`stream_agent` 把图并入多模态消息直通现有 agent；新增 `create_contact` 工具（write_queue）+ `EXECUTORS` 执行器，与 `create_task` 同一确认红线。

**Tech Stack:** FastAPI + deepagents/LangChain（多模态 HumanMessage）、Vue 3 + Element Plus（📎/拖拽/缩略图）、pytest + vitest。

**Spec:** `docs/superpowers/specs/2026-09-29-vision-import-design.md`

## Global Constraints

- `deepagents` 只允许在 `backend/agent/` import（D6.1）；业务代码禁止直接 import。
- 前端契约类型只加在 `frontend/src/api/types.ts`（唯一来源）。
- 前端样式只消费 CSS 变量（`--crm-*`），禁止硬编码颜色/圆角。
- 图片**最多 1 张/条消息**；格式与体积由 `storage.ALLOWED_EXTENSIONS`（.jpg/.jpeg/.png/.webp）与 `MAX_IMAGE_BYTES`（10MB）把守——它们已在 `save_temp` 生效，本计划不重复实现。
- 判权一律走现有机制：临时图本人校验用 `storage.is_own_temp_path`，联系人落库走 `contacts_service.create_contact`（含同名检测 D7，**不得**用 `confirm_duplicate=True` 绕过）。
- 测试库是 `personal_crm_test`；conftest 的环境变量设置在 import app 之前（往 conftest 加 import 必须放其后）。
- 每个方法要有注释（写「为什么」）；每个任务 TDD：先失败测试再实现。

## Review Focus

1. **冒用他人临时图**：请求带他人 `tmp/{other_id}/…` → 必须拒绝（Task 1 的 `test_chat_with_other_users_image_is_404`）。
2. **路径穿越**：`tmp/1/../../secret.png` 字符串前缀能骗过归属检查 → `resolve_within_root` 必须拦下（Task 1 的 `test_chat_with_escape_path_is_422`）。
3. **纯文本消息回归**：加 `images` 后，不带图的消息 content 必须仍是纯字符串（Task 2 的 `test_stream_agent_keeps_plain_text`）。
4. **视觉降级不误伤**：不带图的上游 4xx 仍走通用兜底，只有带图请求给 `vision_unsupported`（Task 3 的 `test_stream_agent_reports_vision_unsupported` 第二段）。
5. **同名保护不被绕过**：确认执行 `create_contact` 撞同名 → 不落库、result 记原因（Task 6 的 `test_approve_create_contact_blocked_by_duplicate`）。

---

### Task 1: `/ai/chat` 契约加 `images` 与图片校验

**Files:**
- Modify: `backend/app/services/storage.py`（新增 `image_mime` 纯函数）
- Modify: `backend/app/modules/ai/api.py`（`ChatIn.images`、`_load_image_data_uris`、chat 端点接线）
- Modify: `backend/agent/runner.py`（`stream_agent` 签名加 `images` 形参，本任务只加参数不使用）
- Test: `backend/tests/test_ai_vision.py`（新建）

**Interfaces:**
- Consumes: `storage.is_own_temp_path(temp_path, user_id) -> bool`、`storage.resolve_within_root(relative) -> Path`（均已存在）
- Produces: `ChatIn.images: list[str] | None`（≤1 项）；`stream_agent(db, user, llm, message, session_id, images: list[str] | None = None)`——`images` 是 **data URI 列表**（Task 2 起使用）；`storage.image_mime(extension: str) -> str`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_ai_vision.py` 新建：

```python
"""视觉导入测试：图片校验、多模态消息、视觉降级。

用一张真实的 1x1 PNG 做夹具——save_temp 有 _ensure_decodable 内容校验，
假字节流过不了上传，这是既有防线的正确行为，测试必须顺着它。
"""

import base64

import pytest
from httpx import AsyncClient

from tests.factories import login_as

pytestmark = pytest.mark.asyncio

# 1x1 透明 PNG（标准 base64），可解码、体积最小
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _upload_image(client: AsyncClient, headers: dict, filename: str = "card.png") -> str:
    """经上传端点把 1x1 PNG 存进本人临时区，返回 temp_path。"""
    response = await client.post(
        "/api/v1/uploads/temp",
        files={"file": (filename, PNG_1PX, "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["temp_path"]


async def test_chat_with_other_users_image_is_404(client, make_user):
    """冒用他人临时图必须 404（同家庭也不行——临时文件是账号私产）。"""
    owner, _ = await make_user(username="owner", password="pw12345678")
    owner_headers = await login_as(client, "owner", "pw12345678")
    temp_path = await _upload_image(client, owner_headers)

    await make_user(username="other", password="pw12345678", family_id=owner.family_id)
    other_headers = await login_as(client, "other", "pw12345678")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": [temp_path]},
        headers=other_headers,
    )
    assert response.status_code == 404


async def test_chat_with_escape_path_is_422(client, make_user):
    """`../` 穿越能骗过字符串前缀归属检查，resolve_within_root 必须拦下。"""
    await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": ["tmp/1/../../secret.png"]},
        headers=headers,
    )
    assert response.status_code == 422


async def test_chat_with_missing_image_is_404(client, make_user):
    """自己临时区里不存在的路径（已过期被清理）→ 404，提示重传。"""
    await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": ["tmp/1/deadbeef.png"]},
        headers=headers,
    )
    assert response.status_code == 404


async def test_chat_rejects_two_images(client, make_user):
    """契约层限 1 张：两张图直接 422（不到业务层）。"""
    await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": ["tmp/1/a.png", "tmp/1/b.png"]},
        headers=headers,
    )
    assert response.status_code == 422
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest -q tests/test_ai_vision.py`
Expected: 4 failed（`images` 未被校验：他人路径/缺失路径返回 200 或 422 形态不对；两张图 200）

- [ ] **Step 3: 实现**

`backend/app/services/storage.py`——在 `ALLOWED_EXTENSIONS` 定义之后加：

```python
# 扩展名 → MIME：随临时文件按原格式喂给视觉模型，与 ALLOWED_EXTENSIONS 白名单一致
_IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def image_mime(extension: str) -> str:
    """按小写扩展名（含点）取 MIME；白名单外的兜底 jpeg——save_temp 已把过格式关。"""
    return _IMAGE_MIME.get(extension.lower(), "image/jpeg")
```

`backend/app/modules/ai/api.py`：

模块头 import 增加（保持字母序）：

```python
import base64
```

```python
from app.core.errors import BusinessError, NotFoundError
```

`ChatIn` 改为：

```python
class ChatIn(BaseModel):
    """对话请求：session_id 由前端生成（一个对话一个 id）；images 为临时区图片路径，最多 1 张。"""

    message: str = Field(min_length=1)
    session_id: str | None = None
    images: list[str] | None = Field(default=None, max_length=1)
```

`_sse` 函数之后加：

```python
def _load_image_data_uris(user: User, images: list[str] | None) -> list[str]:
    """校验并读取请求附图，返回 data URI 列表（直接可喂给视觉模型）。

    三道关：路径必须位于本人临时区（storage.is_own_temp_path）、经
    resolve_within_root 解析（防 ../ 穿越）、文件必须存在；任一不过按 404/422
    拒绝。校验发生在 SSE 响应开始之前——流一开始状态码就改不了了。
    """
    from app.services import storage

    uris: list[str] = []
    for temp_path in images or []:
        normalized = temp_path.strip().lstrip("/")
        if not storage.is_own_temp_path(normalized, user.id):
            raise NotFoundError("图片不存在")
        path = storage.resolve_within_root(normalized)
        if not path.is_file():
            raise NotFoundError("图片不存在或已过期，请重新上传")
        encoded = base64.b64encode(path.read_bytes()).decode()
        uris.append(f"data:{storage.image_mime(path.suffix)};base64,{encoded}")
    return uris
```

`chat` 端点改为（校验提到 `event_stream` 定义之前）：

```python
@router.post("/chat")
async def chat(
    body: ChatIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """agent 对话（SSE 流）：文本增量 / 工具调用状态 / 写入提议 / 错误 / 结束帧。"""
    # 图片校验必须在构造 StreamingResponse 之前：SSE 一旦开始，404 这类
    # 状态码就发不出去了，只能以 JSON 错误响应提前拒绝。
    image_uris = _load_image_data_uris(current_user, body.images)

    async def event_stream():
        session_id = body.session_id or str(uuid.uuid4())
        try:
            # 首轮提问顺手建索引行；已存在则只更新活跃时间。
            # 主键撞车（属于他人）会抛 NotFoundError，一并走下面的错误帧。
            await sessions.ensure_session(db, current_user, session_id, body.message)
            yield _sse({"type": "start", "session_id": session_id})
            llm = await require_llm(db)
            from agent.runner import stream_agent

            async for event in stream_agent(
                db, current_user, llm, body.message, session_id, image_uris
            ):
                yield _sse(event)
        except LLMNotConfiguredError as exc:
            yield _sse({"type": "error", "code": "llm_not_configured", "message": exc.message})
        except BusinessError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception:  # 业务外异常（上游 500 等）也要喂给前端，否则流静默断开
            yield _sse({"type": "error", "message": "对话处理失败，请稍后重试"})
        finally:
            yield _sse({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

`backend/agent/runner.py` 的 `stream_agent` 签名改为（本任务只加形参，函数体不动）：

```python
async def stream_agent(
    db: AsyncSession, user, llm, message: str, session_id: str,
    images: list[str] | None = None,
) -> AsyncIterator[dict]:
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd backend && uv run pytest -q tests/test_ai_vision.py && uv run pytest -q tests/test_ai_chat.py tests/test_agent_runner.py`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/storage.py backend/app/modules/ai/api.py backend/agent/runner.py backend/tests/test_ai_vision.py
git commit -m "feat(ai): chat 契约加 images，本人临时图校验转 data URI"
```

---

### Task 2: runner 构造多模态消息

**Files:**
- Modify: `backend/agent/runner.py`（`stream_agent` 的输入消息构造）
- Test: `backend/tests/test_ai_vision.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `stream_agent(..., images)` 形参（data URI 列表）
- Produces: 带图时 agent 输入消息为 `HumanMessage(content=[{"type":"text",...},{"type":"image_url",...}])`；不带图时 `HumanMessage(content=message)`（纯字符串，行为不变）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_vision.py`：

```python
async def test_stream_agent_builds_multimodal_content(db_session, make_user, monkeypatch):
    """带图对话：content 为 [文本段, 图片段]，data URI 原样透传给模型。"""
    captured: dict = {}

    class _FakeAgent:
        async def astream(self, inputs, **_kwargs):
            captured["messages"] = inputs["messages"]
            chunk_msg = type("M", (), {"content": "ok", "tool_call_chunks": []})()
            yield ((), (chunk_msg, {}))

    monkeypatch.setattr("deepagents.create_deep_agent", lambda **_k: _FakeAgent())
    demo, _ = await make_user(username="demo")
    from agent.runner import stream_agent

    uri = "data:image/png;base64,aGVsbG8="
    events = []
    async for event in stream_agent(
        db_session, demo, llm=object(), message="存下名片", session_id="t1", images=[uri]
    ):
        events.append(event)

    message = captured["messages"][0]
    assert message.content[0] == {"type": "text", "text": "存下名片"}
    assert message.content[1] == {"type": "image_url", "image_url": {"url": uri}}


async def test_stream_agent_keeps_plain_text(db_session, make_user, monkeypatch):
    """不带图的消息 content 仍是纯字符串（多模态改造不回归纯文本路径）。"""
    captured: dict = {}

    class _FakeAgent:
        async def astream(self, inputs, **_kwargs):
            captured["messages"] = inputs["messages"]
            chunk_msg = type("M", (), {"content": "ok", "tool_call_chunks": []})()
            yield ((), (chunk_msg, {}))

    monkeypatch.setattr("deepagents.create_deep_agent", lambda **_k: _FakeAgent())
    demo, _ = await make_user(username="demo")
    from agent.runner import stream_agent

    async for _ in stream_agent(db_session, demo, llm=object(), message="hi", session_id="t2"):
        pass

    assert captured["messages"][0].content == "hi"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest -q tests/test_ai_vision.py::test_stream_agent_builds_multimodal_content tests/test_ai_vision.py::test_stream_agent_keeps_plain_text`
Expected: 第一条 FAIL（content 是字符串 `"存下名片"`，无分段）；第二条 PASS（现状基线）

- [ ] **Step 3: 实现**

`backend/agent/runner.py`——顶部 import 增加：

```python
from langchain_core.messages import HumanMessage
```

`stream_agent` 内、`config = {...}` 行之前加：

```python
    # 图片作为消息内容段直通模型（OpenAI 多模态格式）；带图时整体换 HumanMessage
    # 分段列表，纯文本维持字符串——两条路径构造出的消息对模型等价，但对
    # 「视觉能力检测」（Task 3 判断请求是否带图）是明确信号。
    content: Any = message
    if images:
        content = [{"type": "text", "text": message}] + [
            {"type": "image_url", "image_url": {"url": uri}} for uri in images
        ]
```

`agent.astream(...)` 的输入从 `{"messages": [{"role": "user", "content": message}]}` 改为：

```python
    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=content)]},
        stream_mode=["messages"],
        subgraphs=True,
        config=config,
    ):
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd backend && uv run pytest -q tests/test_ai_vision.py && uv run pytest -q tests/test_agent_runner.py tests/test_ai_chat.py tests/test_ai_history.py`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agent/runner.py backend/tests/test_ai_vision.py
git commit -m "feat(ai): stream_agent 支持多模态消息（图片随对话直通模型）"
```

---

### Task 3: 视觉不支持的专属降级

**Files:**
- Modify: `backend/agent/runner.py`（`stream_agent` 的 astream 循环包 try/except）
- Test: `backend/tests/test_ai_vision.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `images` 形参（判据：非空 = 本次带图）
- Produces: SSE 事件 `{"type": "error", "code": "vision_unsupported", "message": "…（上游：<摘要>）"}`——前端无需新增分支，现有 error 渲染原样显示 message

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_vision.py`：

```python
class _FakeUpstreamError(Exception):
    """模拟 openai 的状态错误：带 status_code 属性（400–499 即客户端错误）。"""

    status_code = 400


async def test_stream_agent_reports_vision_unsupported(db_session, make_user, monkeypatch):
    """带图 + 上游 4xx → 专属 error 帧（code=vision_unsupported，文案含设置页引导）；
    不带图的同款异常向上抛——由 api 层的通用兜底帧处理，不误伤。"""
    class _RejectingAgent:
        async def astream(self, *_args, **_kwargs):
            raise _FakeUpstreamError("image input not supported by this model")

    monkeypatch.setattr("deepagents.create_deep_agent", lambda **_k: _RejectingAgent())
    demo, _ = await make_user(username="demo")
    from agent.runner import stream_agent

    events = [
        event
        async for event in stream_agent(
            db_session, demo, llm=object(), message="x", session_id="t1",
            images=["data:image/png;base64,aGk="],
        )
    ]
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "vision_unsupported"
    assert "不支持图片" in events[-1]["message"]
    assert "image input not supported" in events[-1]["message"]  # 上游摘要便于甄别

    with pytest.raises(_FakeUpstreamError):
        async for _ in stream_agent(db_session, demo, llm=object(), message="x", session_id="t2"):
            pass
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest -q tests/test_ai_vision.py::test_stream_agent_reports_vision_unsupported`
Expected: FAIL——带图分支异常直接抛出（没有 error 帧）

- [ ] **Step 3: 实现**

`backend/agent/runner.py` 的 `stream_agent`：把 `async for chunk in agent.astream(...)` 循环整体包进 try/except（循环体不动）：

```python
    emitted_tools: set[str] = set()
    produced_text = False
    try:
        async for chunk in agent.astream(
            {"messages": [HumanMessage(content=content)]},
            stream_mode=["messages"],
            subgraphs=True,
            config=config,
        ):
            # ……循环体原样保留……
            if not isinstance(chunk, tuple) or len(chunk) < 2:
                continue
            namespace = chunk[0]
            data = chunk[-1]
            if namespace:  # 子代理输出不上屏
                continue

            # messages 模式的 data 形态：langgraph 可能给 (chunk, metadata) 或裸 chunk
            msg = data[0] if isinstance(data, tuple) and len(data) == 2 else data
            text = _extract_text(getattr(msg, "content", None))
            if text:
                produced_text = True
                yield {"type": "text", "delta": text}

            for call in getattr(msg, "tool_call_chunks", None) or []:
                name = call.get("name")
                if name and name not in emitted_tools:
                    emitted_tools.add(name)
                    yield {"type": "tool", "name": name}
                    # 给工具执行让出事件循环（langgraph 内部已 await，此处仅节奏缓冲）
                    await asyncio.sleep(0)
    except Exception as exc:
        # 带图 + 上游 4xx → 大概率模型不支持视觉。给可行动的文案而不是笼统的
        # 「处理失败」；判据是请求特征（images 非空）而非错误文本匹配。
        status = getattr(exc, "status_code", None)
        if images and isinstance(status, int) and 400 <= status < 500:
            yield {
                "type": "error",
                "code": "vision_unsupported",
                "message": f"当前模型不支持图片输入，请在设置页换用支持视觉的模型（上游：{str(exc)[:200]}）",
            }
            return
        raise  # 不带图（或其他异常）照旧抛给 api 层的通用兜底帧
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd backend && uv run pytest -q tests/test_ai_vision.py tests/test_agent_runner.py tests/test_ai_chat.py`
Expected: 全部 PASS（`test_chat_sse_reports_limit_hint_when_silent` 等既有用例不受影响）

- [ ] **Step 5: Commit**

```bash
git add backend/agent/runner.py backend/tests/test_ai_vision.py
git commit -m "feat(ai): 带图请求遇上游 4xx 给 vision_unsupported 专属提示"
```

---

### Task 4: 历史消息的 ［图片］ 标记

**Files:**
- Modify: `backend/agent/runner.py`（`_to_history_messages`）
- Test: `backend/tests/test_ai_history.py`（追加）

**Interfaces:**
- Consumes: Task 2 的消息形态（content 为分段列表的多模态消息会存进 checkpointer）
- Produces: 历史接口输出 `content` 以 `［图片］` 开头（本体不回显）

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_history.py` 末尾：

```python
async def test_history_marks_multimodal_message():
    """带图片分段的消息在历史里加 ［图片］ 前缀（本体不回显，但「有图」这个事实不丢）。"""
    from langchain_core.messages import HumanMessage

    from agent.runner import _to_history_messages

    multimodal = HumanMessage(
        content=[
            {"type": "text", "text": "存下这张名片"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGk="}},
        ]
    )
    items = _to_history_messages([multimodal])
    assert items[0]["role"] == "user"
    assert items[0]["content"] == "［图片］存下这张名片"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest -q tests/test_ai_history.py::test_history_marks_multimodal_message`
Expected: FAIL——content 是 `"存下这张名片"`（无标记）

- [ ] **Step 3: 实现**

`backend/agent/runner.py` 的 `_to_history_messages`，items.append 之前加标记逻辑：

```python
    for message in messages or []:
        role = {"human": "user", "ai": "assistant"}.get(getattr(message, "type", ""))
        if role is None:
            continue
        content = getattr(message, "content", None)
        text = _extract_text(content)
        # 多模态消息（文本+图片分段）：图片本体不进历史（渲染不了也很大），
        # 但「这条消息带过图」的事实要用标记留住，否则用户看历史会莫名断片。
        if isinstance(content, list) and any(
            isinstance(part, dict) and part.get("type") == "image_url" for part in content
        ):
            text = f"［图片］{text}"
        items.append(
            {
                "role": role,
                "content": text,
                "tools": [
                    call.get("name")
                    for call in getattr(message, "tool_calls", None) or []
                    if call.get("name")
                ],
            }
        )
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd backend && uv run pytest -q tests/test_ai_history.py`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agent/runner.py backend/tests/test_ai_history.py
git commit -m "feat(ai): 带图消息进历史时加 ［图片］ 标记"
```

---

### Task 5: `create_contact` 工具（入队）

**Files:**
- Modify: `backend/app/modules/ai/registry.py`（`CreateContactArgs`、`_run_queue_create_contact`、`ALL_TOOLS`）
- Test: `backend/tests/test_ai_tools.py`（追加）

**Interfaces:**
- Consumes: `pending.propose(db, user, tool_name, payload) -> PendingAction`（已存在）
- Produces: `get_tool("create_contact")`（risk=`write_queue`）；提议 payload 键集合：`tier/last_name/first_name` 恒在 + 可选 `nickname/organization/phone/qq/wechat/email/school_name/bio/location`（Task 6 的执行器按此消费）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_ai_tools.py`——`test_registry_completeness` 的集合断言加 `"create_contact"`：

```python
    assert {
        "search_contacts",
        "get_upcoming_todos",
        "get_contact_timeline",
        "get_stats",
        "create_task",
        "create_activity",
        "create_contact",
    } <= set(names)
```

文件末尾追加：

```python
async def test_create_contact_tool_queues_proposal(db_session, make_user):
    """create_contact 进确认队列、不触达联系人表；卡片字段原样进 payload。"""
    demo, _ = await make_user(username="demo")

    out = await _run_tool(
        db_session, demo, "create_contact",
        last_name="王", nickname="王姨", organization="某某中学", phone="13800000000",
    )

    assert "提议" in out

    from sqlalchemy import select

    from app.modules.ai.models import PendingAction

    rows = list((await db_session.execute(select(PendingAction))).scalars())
    assert len(rows) == 1
    assert rows[0].tool_name == "create_contact"
    assert rows[0].payload["tier"] == "direct"
    assert rows[0].payload["phone"] == "13800000000"
    assert rows[0].payload["organization"] == "某某中学"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest -q tests/test_ai_tools.py::test_registry_completeness tests/test_ai_tools.py::test_create_contact_tool_queues_proposal`
Expected: 双 FAIL（`get_tool("create_contact")` 断言工具未注册）

- [ ] **Step 3: 实现**

`backend/app/modules/ai/registry.py`：

import 行 `from pydantic import BaseModel, Field` 改为 `from pydantic import BaseModel, Field, model_validator`。

`CreateActivityArgs` 之后加入参 schema：

```python
class CreateContactArgs(BaseModel):
    """建联系人入参（写入确认队列）：名片/截图上读得到的字段，全部可选。"""

    tier: str = Field(default="direct", description="direct=直接联系人（默认）；信息量少给 edge")
    last_name: str = Field(default="", max_length=50)
    first_name: str = Field(default="", max_length=50)
    nickname: str | None = Field(default=None, max_length=100)
    organization: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    qq: str | None = Field(default=None, max_length=30)
    wechat: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=120)
    school_name: str | None = Field(default=None, max_length=100)
    bio: str | None = None
    location: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_name_presence(self) -> "CreateContactArgs":
        """与 ContactCreate 同一最小信息集：姓、名、昵称至少一项，否则没法定位到人。"""
        if not any(
            [self.last_name.strip(), self.first_name.strip(), (self.nickname or "").strip()]
        ):
            raise ValueError("姓、名、昵称至少填写一项")
        return self
```

`_run_queue_create_activity` 之后加入队函数：

```python
async def _run_queue_create_contact(db: AsyncSession, user, args: CreateContactArgs) -> str:
    """建联系人提议入队：payload 即联系人字段，同名拦截延后到确认执行时。"""
    from app.modules.ai import pending as pending_service

    payload: dict[str, Any] = {
        "tier": args.tier,
        "last_name": args.last_name,
        "first_name": args.first_name,
    }
    for key in (
        "nickname", "organization", "phone", "qq",
        "wechat", "email", "school_name", "bio", "location",
    ):
        value = getattr(args, key)
        if value:
            payload[key] = value
    action = await pending_service.propose(db, user, "create_contact", payload)
    return (
        f"已生成联系人提议（编号 {action.id}，待确认）："
        f"{args.last_name}{args.first_name}{args.nickname or ''}。"
        f"需要用户在界面确认后才会真正创建。"
    )
```

`ALL_TOOLS` 列表末尾（`create_activity` 项之后）追加：

```python
    AiTool(
        name="create_contact",
        description="录入一个新联系人（口述或名片/截图识别均可，需用户确认后生效）；提议前先用 search_contacts 查同名",
        risk="write_queue",
        args_schema=CreateContactArgs,
        run=_run_queue_create_contact,
    ),
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd backend && uv run pytest -q tests/test_ai_tools.py tests/test_semantic.py`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ai/registry.py backend/tests/test_ai_tools.py
git commit -m "feat(ai): create_contact 写工具入确认队列（自动暴露给 /mcp）"
```

---

### Task 6: 执行器（含同名拦截）与系统提示词

**Files:**
- Modify: `backend/app/modules/ai/pending.py`（`_exec_create_contact` + `EXECUTORS`）
- Modify: `backend/agent/runner.py`（`SYSTEM_PROMPT` 追加一条）
- Test: `backend/tests/test_ai_pending.py`（追加）

**Interfaces:**
- Consumes: Task 5 的 payload 键集合；`contacts_service.create_contact(db, user, ContactCreate) -> ContactCreateResponse`（已存在，含同名检测）
- Produces: `EXECUTORS["create_contact"]`——确认后真实落库；同名拦截时 `result = {"ok": False, "error": "同名提醒：…"}`

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_ai_pending.py`（文件已有 `create_contact_for` import）：

```python
async def test_approve_executes_create_contact(db_session, make_user):
    """确认建联系人：走 contacts 正常创建路径，电话落库，归属为提议人（D7）。"""
    demo, _ = await make_user(username="demo")

    action = await pending_service.propose(
        db_session, demo, "create_contact",
        {"tier": "direct", "last_name": "王", "nickname": "王姨", "phone": "13800000000"},
    )
    approved = await pending_service.approve(db_session, demo, action.id)

    assert approved.status == "executed"
    assert approved.result["ok"] is True
    assert "王姨" in approved.result["message"]

    from sqlalchemy import select

    from app.modules.contacts.models import Contact

    contacts = list((await db_session.execute(select(Contact))).scalars())
    assert len(contacts) == 1
    assert contacts[0].phone == "13800000000"
    assert contacts[0].owner_user_id == demo.id


async def test_approve_create_contact_blocked_by_duplicate(db_session, make_user):
    """撞同名：不落库、result 记原因——确认执行不得绕过同名保护（D7）。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, last_name="王", first_name="", nickname="王姨")

    action = await pending_service.propose(
        db_session, demo, "create_contact",
        {"tier": "direct", "last_name": "王", "nickname": "王姨"},
    )
    approved = await pending_service.approve(db_session, demo, action.id)

    assert approved.status == "executed"
    assert approved.result["ok"] is False
    assert "同名" in approved.result["error"]

    from sqlalchemy import func, select

    from app.modules.contacts.models import Contact

    count = (await db_session.execute(select(func.count()).select_from(Contact))).scalar_one()
    assert count == 1  # 只有预置那一条，提议没有落库
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && uv run pytest -q tests/test_ai_pending.py::test_approve_executes_create_contact tests/test_ai_pending.py::test_approve_create_contact_blocked_by_duplicate`
Expected: 双 FAIL（`EXECUTORS.get` 返回 None → result 记「未知工具 create_contact」）

- [ ] **Step 3: 实现**

`backend/app/modules/ai/pending.py`——`_exec_create_activity` 之后加执行器，`EXECUTORS` 注册：

```python
async def _exec_create_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行建联系人：走 contacts 正常创建（自带同名检测 D7）；被拦截就把提醒
    写进 result——绝不用 confirm_duplicate=True 绕过，同名合并是人该做的决定。"""
    from app.modules.contacts import service as contacts_service
    from app.modules.contacts.schemas import ContactCreate

    response = await contacts_service.create_contact(db, user, ContactCreate(**payload))
    if not response.created:
        names = "、".join(w.display_name for w in response.duplicate_warnings) or "同名联系人"
        return {
            "ok": False,
            "error": f"同名提醒：{names} 已存在，未创建。可拒绝此提议，或去名册处理",
        }
    assert response.contact is not None
    return {
        "ok": True,
        "message": f"联系人已创建（id={response.contact.id}）：{response.contact.display_name}",
    }


EXECUTORS = {
    "create_task": _exec_create_task,
    "create_activity": _exec_create_activity,
    "create_contact": _exec_create_contact,
}
```

`backend/agent/runner.py` 的 `SYSTEM_PROMPT` 回答原则追加第 5 条：

```python
5. 用户发来名片/聊天截图要求录入时：先用 search_contacts 查同名，再调 create_contact 生成提议（需用户确认后生效）；图里没有的字段留空，禁止编造。
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd backend && uv run pytest -q tests/test_ai_pending.py tests/test_ai_tools.py && uv run ruff check .`
Expected: 全部 PASS，ruff 干净

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ai/pending.py backend/agent/runner.py backend/tests/test_ai_pending.py
git commit -m "feat(ai): create_contact 执行器（同名拦截不落库）+ 提示词补录入策略"
```

---

### Task 7: 前端——chat 带 images 与上传交互

**Files:**
- Modify: `frontend/src/api/ai.ts`（`chat` 加第 4 参）
- Modify: `frontend/src/components/AgentChat.vue`（📎/拖拽/预览/发送）
- Test: `frontend/tests/agentChat.spec.ts`（新建）

**Interfaces:**
- Consumes: `api.uploadTemp(file) -> { temp_path }`（client.ts 已有）；后端 `ChatIn.images`
- Produces: `aiApi.chat(message, sessionId, onEvent, images?: string[])`；AgentChat 内部状态 `pendingImage: { tempPath: string; previewUrl: string } | null`；模板锚点 `[data-test="pending-image"]`、`[data-test="send"]`

- [ ] **Step 1: 写失败测试**

`frontend/tests/agentChat.spec.ts` 新建：

```typescript
/** Agent 对话组件测试：图片上传预览、发送带图、视觉降级文案、提议渲染。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { chat, pendingList, uploadTemp } = vi.hoisted(() => ({
  chat: vi.fn(),
  pendingList: vi.fn(),
  uploadTemp: vi.fn(),
}))
vi.mock('@/api/ai', () => ({ aiApi: { chat, pendingList } }))
// 保留真实 ApiError（组件用 instanceof 判错），只替换 uploadTemp
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, api: { ...actual.api, uploadTemp } }
})

import AgentChat from '@/components/AgentChat.vue'

const MOUNT_OPTIONS = {
  props: { sessionId: 's1' },
  global: { plugins: [ElementPlus] },
}

beforeEach(() => {
  chat.mockReset()
  pendingList.mockReset().mockResolvedValue([])
  uploadTemp.mockReset().mockResolvedValue({ temp_path: 'tmp/9/card.png' })
})

/** 模拟选择一张图片（jsdom 不能直接赋 files，用 defineProperty）。 */
async function pickImage(wrapper: ReturnType<typeof mount>): Promise<void> {
  const input = wrapper.find('input[type="file"]')
  const file = new File(['x'], 'card.png', { type: 'image/png' })
  Object.defineProperty(input.element, 'files', { value: [file] })
  await input.trigger('change')
}

describe('AgentChat 图片', () => {
  it('选图即传临时区并显示预览', async () => {
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    await pickImage(wrapper)
    await flushPromises()

    expect(uploadTemp).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="pending-image"]').exists()).toBe(true)
  })

  it('发送时带图片路径并清空预览，气泡留缩略图', async () => {
    chat.mockImplementation(async (_t, _s, onEvent) => {
      onEvent({ type: 'start', session_id: 's1' })
      onEvent({ type: 'done' })
    })
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    await pickImage(wrapper)
    await wrapper.get('[data-test="chat-input"]').setValue('存下名片')
    await wrapper.get('[data-test="send"]').trigger('click')
    await flushPromises()

    expect(chat).toHaveBeenCalledWith('存下名片', 's1', expect.any(Function), ['tmp/9/card.png'])
    expect(wrapper.find('[data-test="pending-image"]').exists()).toBe(false)
    expect(wrapper.find('.msg-image').exists()).toBe(true)
  })

  it('视觉不支持的错误帧原样显示引导文案', async () => {
    chat.mockImplementation(async (_t, _s, onEvent) => {
      onEvent({ type: 'start', session_id: 's1' })
      onEvent({
        type: 'error',
        code: 'vision_unsupported',
        message: '当前模型不支持图片输入，请在设置页换用支持视觉的模型（上游：image input not supported）',
      })
      onEvent({ type: 'done' })
    })
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    await wrapper.get('[data-test="chat-input"]').setValue('存下名片')
    await wrapper.get('[data-test="send"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('不支持图片输入')
    expect(wrapper.text()).toContain('设置页')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run tests/agentChat.spec.ts`
Expected: FAIL（找不到 `input[type="file"]` / `[data-test="send"]`）

- [ ] **Step 3: 实现**

`frontend/src/api/ai.ts` 的 `chat` 签名与请求体改为：

```typescript
  chat: async (
    message: string,
    sessionId: string | null,
    onEvent: (event: ChatStreamEvent) => void,
    images: string[] = [],
  ) => {
    const auth = await import('@/stores/auth')
    const store = auth.useAuthStore()
    const response = await fetch('/api/v1/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${store.token}` },
      // images 为空时不带该字段（undefined 不序列化），后端契约向后兼容
      body: JSON.stringify({
        message,
        session_id: sessionId,
        images: images.length ? images : undefined,
      }),
    })
    // ……以下读取循环原样保留……
```

`frontend/src/components/AgentChat.vue`：

script 段——import 增加 `import { api } from '@/api/client'`；`ChatMessage` 接口加可选字段：

```typescript
interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tools: string[]
  /** 本轮带图时的本地预览地址（仅本次会话内存里；历史载入无图，见后端 ［图片］ 标记）。 */
  imagePreview?: string
}
```

状态与函数（`activeTool` 定义之后）：

```typescript
const fileInput = ref<HTMLInputElement | null>(null)
const uploadingImage = ref(false)
/** 待发送图片：上传临时区后留路径 + 本地预览；只保留最后一张，发送后清空。 */
const pendingImage = ref<{ tempPath: string; previewUrl: string } | null>(null)

/** 选中/拖入图片：先传临时区再预览。新图替换旧图，并回收旧预览的 object URL。 */
async function acceptImage(file: File): Promise<void> {
  uploadingImage.value = true
  const previous = pendingImage.value
  try {
    const { temp_path } = await api.uploadTemp(file)
    if (previous) URL.revokeObjectURL(previous.previewUrl)
    pendingImage.value = { tempPath: temp_path, previewUrl: URL.createObjectURL(file) }
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '图片上传失败')
  } finally {
    uploadingImage.value = false
  }
}

function clearImage(): void {
  if (pendingImage.value) URL.revokeObjectURL(pendingImage.value.previewUrl)
  pendingImage.value = null
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void acceptImage(file)
  input.value = '' // 允许再次选择同一张图
}

function onDrop(event: DragEvent): void {
  const file = event.dataTransfer?.files?.[0]
  if (file) void acceptImage(file)
}
```

`send()` 改为（只列变化处）：

```typescript
async function send(): Promise<void> {
  const text = input.value.trim()
  // 带图可以没有文字——默认给一句指令，后端 message 契约要求非空
  if ((!text && !pendingImage.value) || streaming.value) return
  input.value = ''
  const imageTemp = pendingImage.value?.tempPath
  const preview = pendingImage.value?.previewUrl
  clearImage()
  messages.value.push({ role: 'user', content: text, tools: [], imagePreview: preview })
  const reply = appendAssistant()
  streaming.value = true
  activeTool.value = null
  try {
    await aiApi.chat(
      text || '帮我看看这张图',
      props.sessionId,
      (event: ChatStreamEvent) => handleEvent(event, reply),
      imageTemp ? [imageTemp] : [],
    )
  } catch (error) {
    reply.content += error instanceof Error ? error.message : '对话请求失败'
  } finally {
    streaming.value = false
    activeTool.value = null
    await scrollToBottom()
    await refreshPending()
    emit('updated')
  }
}
```

template——根元素挂拖拽，composer 区加 📎 与预览条，发送按钮加 `data-test`：

```vue
  <div class="agent-chat" @dragover.prevent @drop.prevent="onDrop">
```

```vue
    <div v-if="pendingImage" class="image-preview" data-test="pending-image">
      <img :src="pendingImage.previewUrl" alt="待发送图片" />
      <el-button text size="small" @click="clearImage">移除</el-button>
    </div>

    <div class="composer">
      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        class="file-hidden"
        @change="onFileChange"
      />
      <el-button text :loading="uploadingImage" @click="fileInput?.click()">📎</el-button>
      <!-- el-input 上加 data-test（会透传到内层 input，选择器直接可用，见 SearchPage 先例）；
           其余属性保持现状：v-model="input"、placeholder、:disabled="streaming"、@keydown.enter.prevent="send" -->
      <el-input
        v-model="input"
        data-test="chat-input"
        :placeholder="streaming ? '助手思考中…' : '问我任何事，或让我帮你记一笔'"
        :disabled="streaming"
        @keydown.enter.prevent="send"
      />
      <el-button type="primary" :loading="streaming" :disabled="!input.trim()" data-test="send" @click="send">
        发送
      </el-button>
    </div>
```

消息气泡（user 消息在气泡上方渲染缩略图）：

```vue
        <img v-if="item.imagePreview" class="msg-image" :src="item.imagePreview" alt="附图" />
        <div class="msg-bubble">{{ item.content }}<span v-if="streaming && index === messages.length - 1 && item.role === 'assistant'" class="cursor">▍</span></div>
```

style 段追加：

```css
.file-hidden {
  display: none;
}
.image-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px 8px;
}
.image-preview img {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: var(--crm-radius-control);
  border: 1px solid var(--crm-line);
}
.msg-image {
  max-width: 180px;
  border-radius: var(--crm-radius-control);
  border: 1px solid var(--crm-line);
}
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 全部 PASS，vue-tsc 无错

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ai.ts frontend/src/components/AgentChat.vue frontend/tests/agentChat.spec.ts
git commit -m "feat(frontend): 助理对话框支持传图（📎/拖拽/预览，发送带 images）"
```

---

### Task 8: 确认面板的中文渲染

**Files:**
- Modify: `frontend/src/components/AgentChat.vue`（标签映射 + `payloadText` 分流 + 工具名中文）
- Test: `frontend/tests/agentChat.spec.ts`（追加）

**Interfaces:**
- Consumes: Task 5 的 payload 键集合（tier/last_name/first_name/nickname/organization/phone/qq/wechat/email/school_name/bio/location）
- Produces: 无（纯展示）

- [ ] **Step 1: 写失败测试**

追加到 `frontend/tests/agentChat.spec.ts` 末尾：

```typescript
describe('AgentChat 确认面板', () => {
  it('create_contact 提议用中文标签渲染（层级转译为直接/边缘）', async () => {
    pendingList.mockResolvedValue([
      {
        id: 1,
        tool_name: 'create_contact',
        payload: { tier: 'direct', last_name: '王', nickname: '王姨', phone: '13800000000' },
        status: 'pending',
        result: null,
        created_at: '2026-09-30T00:00:00Z',
      },
    ])
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    const text = wrapper.get('.pending-item').text()
    expect(text).toContain('建联系人')
    expect(text).toContain('层级: 直接')
    expect(text).toContain('昵称: 王姨')
    expect(text).toContain('电话: 13800000000')
    expect(text).not.toContain('phone:')
  })

  it('其他工具提议维持键值拼写，工具名走中文映射', async () => {
    pendingList.mockResolvedValue([
      {
        id: 2,
        tool_name: 'create_task',
        payload: { title: '给老爸打电话' },
        status: 'pending',
        result: null,
        created_at: '2026-09-30T00:00:00Z',
      },
    ])
    const wrapper = mount(AgentChat, MOUNT_OPTIONS)
    await flushPromises()

    expect(wrapper.get('.pending-item').text()).toContain('title: 给老爸打电话')
    expect(wrapper.text()).toContain('建待办')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run tests/agentChat.spec.ts`
Expected: 新增两条 FAIL（现在是 `tier: direct` / `create_contact` 原样）

- [ ] **Step 3: 实现**

`frontend/src/components/AgentChat.vue` script 段（`payloadText` 之前）：

```typescript
/** 工具名 → 中文（确认面板标题）；未映射的新工具回退原名。 */
const TOOL_LABELS: Record<string, string> = {
  create_task: '建待办',
  create_activity: '记活动',
  create_contact: '建联系人',
}
const CONTACT_FIELD_LABELS: Record<string, string> = {
  tier: '层级', last_name: '姓', first_name: '名', nickname: '昵称',
  organization: '单位', phone: '电话', qq: 'QQ', wechat: '微信',
  email: '邮箱', school_name: '院校', location: '所在地', bio: '备注',
}
const CONTACT_TIER_LABELS: Record<string, string> = { direct: '直接', edge: '边缘' }

/** create_contact 提议用中文标签渲染——确认的前提是看懂在确认什么。 */
function contactPayloadText(payload: Record<string, unknown>): string {
  return Object.entries(payload)
    .map(([key, value]) => {
      const shown = Array.isArray(value)
        ? value.join('、')
        : CONTACT_TIER_LABELS[String(value)] ?? String(value ?? '')
      return `${CONTACT_FIELD_LABELS[key] ?? key}: ${shown}`
    })
    .join(' · ')
}
```

`payloadText` 开头分流：

```typescript
function payloadText(action: PendingActionOut): string {
  if (action.tool_name === 'create_contact') return contactPayloadText(action.payload)
  const parts = Object.entries(action.payload).map(([key, value]) => {
    const shown = Array.isArray(value) ? value.join('、') : String(value ?? '')
    return `${key}: ${shown}`
  })
  return parts.join(' · ')
}
```

template 的工具 tag：

```vue
          <el-tag size="small" type="warning">{{ TOOL_LABELS[action.tool_name] ?? action.tool_name }}</el-tag>
```

- [ ] **Step 4: 跑测试确认通过 + 无回归**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 全部 PASS，vue-tsc 无错

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AgentChat.vue frontend/tests/agentChat.spec.ts
git commit -m "feat(frontend): 确认面板对建联系人提议用中文标签渲染"
```

---

### Task 9: 文档登记与全量验证

**Files:**
- Modify: `TECH_DECISIONS.md`、`ARCHITECTURE.md`、`DESIGN.md`、`ROADMAP.md`

**Interfaces:**
- Consumes: Task 1–8 的最终形态（契约 `ChatIn.images`、工具 `create_contact`、错误码 `vision_unsupported`）
- Produces: 事实源文档与代码一致

- [ ] **Step 1: TECH_DECISIONS.md**

决策总览表追加一行（日期 2026-09-30）：

```markdown
| D21 | **视觉导入**：与 agent 同一 LLM（被动检测视觉能力，不做模型名启发式）；图片作多模态消息直通 agent；落库一律经既有确认队列（不引入 interrupt） | ✅ | 2026-09-30 |
```

文件末尾（D20 小节之后）加小节：

```markdown
## D21 视觉导入：同模型 + 直通 agent + 既有确认队列 ✅（2026-09-30，落实 R3）

- **同模型**：视觉解析复用运行时 LLM 配置（D6.2），不新增配置项；模型不支持视觉以真实上游 4xx 为准，chat 对带图请求给 `vision_unsupported` 专属错误帧（附上游摘要），不做模型名启发式。
- **直通 agent**：图片按 OpenAI 多模态格式并入消息（`POST /ai/chat` 的 `images` 字段，≤1 张 data URI），agent 自主选择工具；不建独立抽取管线——那会绕开工具注册表与 /mcp。
- **确认走既有队列**：新工具 `create_contact`（write_queue）与 `create_task`/`create_activity` 同一红线，`EXECUTORS` 执行器走 `contacts_service.create_contact`，同名拦截不绕过。
- 影响图片来源：`images` 指向本人临时区（`POST /uploads/temp`，D18），端点校验归属/穿越/存在性后转 data URI，临时文件由既有 TTL 清理回收。
```

- [ ] **Step 2: ARCHITECTURE.md**

第 4 节 `/api/v1/ai、/mcp` 行的「SSE 对话」描述改为（追加 images 与 create_contact）：

```
✅ SSE 对话（POST /ai/chat，请求带 `session_id`、缺失则服务端补；`images` ≤1 张本人临时图，
服务端转 data URI 以多模态消息直通 agent）、……、写入提议确认（/ai/pending/*，含 create_contact）
```

第 1 节 ai 模块「职责与边界」末尾补一句：`；视觉导入（图片随对话进 agent，识别产物走写入确认队列）`。

- [ ] **Step 3: DESIGN.md**

「设置页 · 外部接入」小节之后追加：

```markdown
## 助理页 · 传图（2026-09-30）

- **入口**：输入区 📎 按钮（隐藏 `input[type=file]`，accept jpeg/png/webp）+ 对话区整体拖拽；选中即传临时区，输入区上方出 72px 缩略图预览条（可移除），只保留最后一张。
- **气泡**：本轮用户消息在气泡上方显示附图（最大宽 180px，`--crm-line` 描边 + `--crm-radius-control` 圆角）；历史消息不回显图片本体，以 `［图片］` 文本标记。
- **确认面板**：`create_contact` 提议用中文标签（层级转译为「直接/边缘」），其余工具维持键值拼写；工具名显示中文（建待办/记活动/建联系人）。
```

- [ ] **Step 4: ROADMAP.md**

Level 4 表「截图导入」行改为：

```markdown
| 截图导入 | ✅ 已落地（2026-09-30，D21）：助理对话框传图 → 同一 LLM 多模态识别 → `create_contact` 提议 → 确认队列落库；不支持视觉的模型给专属提示 |
```

- [ ] **Step 5: 全量验证**

```bash
cd backend && uv run pytest -q && uv run ruff check .
cd ../frontend && npm run test && npm run build
```

Expected: 后端全绿（原 204 + 新增约 12 条）、ruff 干净、前端全绿（原 36 + 新增 7 条）、build 通过

- [ ] **Step 6: 端到端核验（需用户配合：设置页配置一个支持视觉的模型）**

```bash
lsof -ti :8100 | xargs kill; sleep 2
cd backend && nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8100 > /tmp/crm-backend.log 2>&1 &
```

在助理页逐项核验：
1. 📎 选一张名片图 → 缩略图预览出现；点「移除」→ 消失。
2. 带图发「存下这张名片」→ 流式回复 + 「正在调用 create_contact…」→ 确认面板出现中文提议（姓名/电话…）。
3. **点「确认执行」** → 回复 ✅ 已创建 → 名册里能搜到该人、电话在详情数据里。
4. 拒绝路径：再传一张图 → 拒绝提议 → 名册无此人。
5. 同名路径：对已有联系人再发一张同名图 → 确认 → 回复 ⚠ 同名提醒，名册无第二条。
6. 把 LLM 换成纯文本模型再发图 → 回复「当前模型不支持图片输入…」；换回后恢复正常。
7. 刷新页面进该会话 → 历史里该条显示 `［图片］` 标记。

- [ ] **Step 7: Commit**

```bash
git add TECH_DECISIONS.md ARCHITECTURE.md DESIGN.md ROADMAP.md
git commit -m "docs: 登记 D21 视觉导入与接口/样式/路线图同步"
```
