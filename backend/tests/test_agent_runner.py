"""agent 运行器测试：单次提问的 LLM 调用上限中间件被正确注入（官方中间件）。"""

import json
from contextlib import asynccontextmanager

import pytest

pytestmark = pytest.mark.asyncio


def _patch_connected_checkpointer(monkeypatch):
    """把 from_conn_string 换成桩实现：不碰真库，且记录连接何时被关闭。

    返回桩对象——测试用它区分「连接还活着」与「连接已被关掉」两种交接状态。
    """

    class _Stub:
        """假装已连上数据库的 checkpointer：让 setup 那一段走通即可。"""

        def __init__(self) -> None:
            self.closed = False

        async def setup(self) -> None:
            return None

    stub = _Stub()

    @asynccontextmanager
    async def _fake_from_conn_string(_dsn):
        try:
            yield stub
        finally:
            stub.closed = True

    monkeypatch.setattr(
        "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver.from_conn_string",
        _fake_from_conn_string,
    )
    return stub


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
    async for event in stream_agent(
        db_session, demo, llm=object(), message="hi", session_id="t1"
    ):
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


async def test_checkpointer_defaults_to_in_memory():
    """未注入时退回进程内内存：测试与降级路径都依赖这一点。"""
    import agent.runner as runner

    runner._CHECKPOINTER = None
    checkpointer = runner.get_checkpointer()

    assert checkpointer is not None
    assert type(checkpointer).__name__ == "InMemorySaver"


async def test_set_checkpointer_overrides_default():
    """注入后 get_checkpointer 返回注入的实例（生产走这条）。"""
    from langgraph.checkpoint.memory import InMemorySaver

    import agent.runner as runner

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


async def test_checkpointer_open_propagates_body_errors(monkeypatch):
    """上下文体内的异常必须原样传播——降级分支只该包住「建立连接 + setup」。

    yield 若落在 try 内，contextlib 会把体里的异常 athrow 回生成器，被 except
    捕获后二次 yield，原始异常被换成 RuntimeError("generator didn't stop")，
    故障真相与 traceback 一起丢失。
    """

    class _DownstreamError(RuntimeError):
        """模拟启动流程中其它子系统的故障。"""

    from app import main

    _patch_connected_checkpointer(monkeypatch)

    with pytest.raises(_DownstreamError):
        async with main._open_checkpointer():
            raise _DownstreamError("下游子系统启动失败")


async def test_checkpointer_open_keeps_connection_alive_for_body(monkeypatch):
    """交接给应用时连接必须还活着（checkpointer 全程持有这一条连接）。

    把 yield 挪出 `async with from_conn_string(...)` 会让连接在应用拿到它之前
    关闭——持久化要等到第一次提问才炸，而不是启动时就暴露。
    """
    from app import main

    stub = _patch_connected_checkpointer(monkeypatch)

    async with main._open_checkpointer() as checkpointer:
        assert checkpointer is stub
        assert stub.closed is False

    assert stub.closed is True  # 正常退出时要关闭连接，不泄漏
