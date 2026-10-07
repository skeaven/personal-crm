"""AI 对话测试：未配置 LLM 的降级契约、事件流透传、提议确认的 HTTP 全流程。"""

import json

import pytest

pytestmark = pytest.mark.asyncio


async def _read_sse(response) -> list[dict]:
    """把 SSE 响应体解析为事件列表。"""
    events = []
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


async def test_chat_without_llm_reports_config_error(client, make_user, login_headers):
    """D6.2 降级契约：未配置 LLM 时对话返回明确的配置引导错误（HTTP 200 + SSE error 帧）。"""
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    resp = await client.post(
        "/api/v1/ai/chat", json={"message": "帮我查一下待办"}, headers=headers
    )
    assert resp.status_code == 200
    events = await _read_sse(resp)
    codes = [e.get("code") for e in events if e["type"] == "error"]
    assert "llm_not_configured" in codes
    assert events[-1]["type"] == "done"


async def test_chat_streams_stub_events(client, make_user, login_headers, monkeypatch):
    """事件流透传：stub 掉 agent 运行器后，text/tool 事件原样到达前端。"""
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    async def fake_stream(db, user, llm, message, session_id, images=None):
        yield {"type": "tool", "name": "get_upcoming_todos"}
        yield {"type": "text", "delta": "你有 "}
        yield {"type": "text", "delta": "3 件待办"}

    monkeypatch.setattr("agent.runner.stream_agent", fake_stream)
    await client.put(
        "/api/v1/settings/ai",
        json={"base_url": "http://127.0.0.1:9/v1", "api_key": "sk-x", "model": "m"},
        headers=headers,
    )

    resp = await client.post(
        "/api/v1/ai/chat", json={"message": "我今天有什么事？"}, headers=headers
    )
    events = await _read_sse(resp)
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done"
    texts = "".join(e["delta"] for e in events if e["type"] == "text")
    assert texts == "你有 3 件待办"
    assert {"type": "tool", "name": "get_upcoming_todos"} in events


async def test_chat_emits_error_and_done_on_unexpected_exception(
    client, make_user, login_headers, monkeypatch
):
    """agent 抛业务外异常（如 LLM API 500）时，客户端仍要拿到 error 帧与结束帧。

    否则前端拿到的是断掉的无提示流；且索引行已被 rollback、checkpointer 已落盘，
    变成不可达的遗孤对话（Review Focus 复审 #1）。
    """
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    called = {"hit": False}

    async def exploding_stream(db, user, llm, message, session_id, images=None):
        called["hit"] = True
        raise RuntimeError("upstream 500")
        yield  # pragma: no cover

    monkeypatch.setattr("agent.runner.stream_agent", exploding_stream)
    await client.put(
        "/api/v1/settings/ai",
        json={"base_url": "http://127.0.0.1:9/v1", "api_key": "sk-x", "model": "m"},
        headers=headers,
    )

    resp = await client.post(
        "/api/v1/ai/chat",
        json={"message": "触发异常", "session_id": "sess-boom"},
        headers=headers,
    )

    assert resp.status_code == 200
    events = await _read_sse(resp)
    assert called["hit"], "stub 没被调用——签名不匹配时 TypeError 会被兜成同一个错误帧，用例空转"
    assert any(e["type"] == "error" for e in events)
    assert events[-1]["type"] == "done"


async def test_pending_flow_http(client, make_user, login_headers):
    """提议确认 HTTP 全流程：入队（提交）→ 列表可见 → 确认执行 → 待办真实落库。"""
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    from tests.factories import create_contact_for

    father = await create_contact_for(demo, name="陈建国", nickname="老爸")

    from app.core.db import get_session_factory
    from app.modules.ai import pending as pending_service

    # 入队（独立会话 + 提交，模拟 agent 工具的自管会话语义）
    factory = get_session_factory()
    async with factory() as session:
        action = await pending_service.propose(
            session, demo, "create_task",
            {"title": "给老爸打电话", "contact_id": father.id, "due_at": "2026-09-30"},
        )
        await session.commit()
    action_id = action.id

    listed = (await client.get("/api/v1/ai/pending", headers=headers)).json()
    assert [item["id"] for item in listed] == [action_id]

    approved = await client.post(f"/api/v1/ai/pending/{action_id}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "executed"
    assert approved.json()["result"]["ok"] is True

    from sqlalchemy import select

    from app.modules.records.models import Task

    async with factory() as session:
        tasks = list((await session.execute(select(Task))).scalars())
        assert len(tasks) == 1 and tasks[0].contact_id == father.id


async def test_chat_creates_session_index_on_first_turn(client, login_headers, make_user):
    """首轮提问要顺手建立会话索引行，否则会话列表里永远看不到它（Review Focus #4）。"""
    from app.core.db import get_session_factory
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
