"""agent 运行器测试：单次提问的 LLM 调用上限中间件被正确注入（官方中间件）。"""

import json

import pytest

pytestmark = pytest.mark.asyncio


async def test_stream_agent_injects_model_call_limit(db_session, make_user, monkeypatch):
    """create_deep_agent 收到 ModelCallLimitMiddleware(run_limit=10, exit_behavior='end')。"""
    captured: dict = {}

    class _FakeAgent:
        """最小 agent 桩：记录构造参数并产出一条文本事件。"""

        def __init__(self, kwargs) -> None:
            captured.update(kwargs)

        async def astream(self, *_args, **_kwargs):
            # messages 模式的真实形态：(namespace, (message_chunk, metadata))
            chunk_msg = type("M", (), {"content": "ok", "tool_call_chunks": []})()
            yield ((), (chunk_msg, {}))

    def fake_create_deep_agent(**kwargs):
        return _FakeAgent(kwargs)

    monkeypatch.setattr("deepagents.create_deep_agent", fake_create_deep_agent)

    demo, _ = await make_user(username="demo")
    from agent.runner import MODEL_CALL_LIMIT, stream_agent

    events = []
    async for event in stream_agent(db_session, demo, llm=object(), message="hi", thread_id="t1"):
        events.append(event)

    middleware = captured["middleware"]
    assert len(middleware) == 1
    assert middleware[0].run_limit == MODEL_CALL_LIMIT == 10
    assert middleware[0].exit_behavior == "end"
    # 事件流不回归
    assert {"type": "text", "delta": "ok"} in events


async def test_chat_sse_reports_limit_hint_when_silent(
    client, make_user, login_headers, monkeypatch
):
    """流结束时零文本输出（如超限终止）→ 前端收到一句上限说明。

    stub 更底层的 deepagents.create_deep_agent：只产生工具调用、无文本，
    让 runner 的真实兜底逻辑执行。
    """
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    class _SilentAgent:
        async def astream(self, *_args, **_kwargs):
            chunk_msg = type(
                "M", (), {"content": "", "tool_call_chunks": [{"name": "get_stats"}]}
            )()
            yield ((), (chunk_msg, {}))

    monkeypatch.setattr("deepagents.create_deep_agent", lambda **_k: _SilentAgent())
    await client.put(
        "/api/v1/settings/ai",
        json={"base_url": "http://127.0.0.1:9/v1", "api_key": "sk-x", "model": "m"},
        headers=headers,
    )

    resp = await client.post("/api/v1/ai/chat", json={"message": "复杂问题"}, headers=headers)
    events = []
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    texts = "".join(e["delta"] for e in events if e["type"] == "text")
    assert "上限" in texts
    tools = [e["name"] for e in events if e["type"] == "tool"]
    assert tools == ["get_stats"]
