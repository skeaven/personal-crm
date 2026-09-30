"""历史消息读取测试：角色映射、工具提取、归属隔离。"""

import pytest

pytestmark = pytest.mark.asyncio


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
    new_versions = {"__start__": 2, "messages": 3}
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    metadata = {"source": "input", "step": 0, "parents": {}}
    await checkpointer.aput(config, checkpoint, metadata, new_versions)


async def test_load_history_maps_roles_and_skips_tool_messages(checkpointer):
    """human→user、ai→assistant；工具消息不进历史（调用已记在 ai 消息上）。"""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from agent.runner import load_history

    await _write_thread(
        checkpointer,
        "1:s1",
        [
            HumanMessage("老爸最近怎么样"),
            AIMessage("我查一下"),
            ToolMessage("ok", tool_call_id="t1"),
        ],
    )

    history = await load_history("s1", user_id=1)

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "老爸最近怎么样"


async def test_load_history_extracts_tool_calls(checkpointer):
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


async def test_load_history_reads_graph_run_thread(checkpointer):
    """回归：真实跑过图的 thread 也要能读出历史。

    上面几个用例手搓了「channel_values 里放全量 messages」的 checkpoint，而
    deepagents 把 messages 声明为 DeltaChannel：图正常跑完后 channel_values 里
    根本没有 messages，直接读它必然得到空历史（线上历史读空即此因）。
    这里用假模型驱动真图跑一轮，再读历史。
    """
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class _EchoModel(BaseChatModel):
        """不发声的假模型：只为把图跑起来产生 checkpoint，不产生真实调用。"""

        @property
        def _llm_type(self) -> str:
            return "echo"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage("我查一下"))])

        def bind_tools(self, tools, **kwargs):
            return self

    from deepagents import create_deep_agent

    from agent.runner import load_history

    agent = create_deep_agent(
        model=_EchoModel(), tools=[], system_prompt="x", checkpointer=checkpointer
    )
    config = {"configurable": {"thread_id": "1:s3"}}
    async for _ in agent.astream(
        {"messages": [{"role": "user", "content": "老爸最近怎么样"}]},
        stream_mode=["messages"],
        config=config,
    ):
        pass

    history = await load_history("s3", user_id=1)

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "老爸最近怎么样"


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
