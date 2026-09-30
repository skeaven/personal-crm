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
    demo, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        # 路径带本人 id 通过归属前缀，再用 ../ 逃出临时区
        # 三层 ../ 才真正逃出临时区（两层恰好退回根目录内，本就不该拦）
        json={"message": "存下名片", "images": [f"tmp/{demo.id}/../../../secret.png"]},
        headers=headers,
    )
    assert response.status_code == 422


async def test_chat_with_missing_image_is_404(client, make_user):
    """自己临时区里不存在的路径（已过期被清理）→ 404，提示重传。"""
    demo, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "存下名片", "images": [f"tmp/{demo.id}/deadbeef.png"]},
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


class _FakeUpstreamError(Exception):
    """模拟 openai 的状态错误：带 status_code 属性（400–499 即客户端错误）。"""

    status_code = 400


async def test_stream_agent_reports_vision_unsupported(db_session, make_user, monkeypatch):
    """带图 + 上游 4xx → 专属 error 帧（code=vision_unsupported，文案含设置页引导）；
    不带图的同款异常向上抛——由 api 层的通用兜底帧处理，不误伤。"""

    class _RejectingAgent:
        async def astream(self, *_args, **_kwargs):
            raise _FakeUpstreamError("image input not supported by this model")
            yield  # 不可达：仅为让函数成为 async generator（与真实 astream 同形）

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
