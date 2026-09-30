"""agent 运行器：deepagents 的唯一封装点（D6.1 隔离层）。

职责：
1. 把 ai/registry 的工具适配为 langchain 工具（以发起用户身份执行，D7）；
2. 构造 deepagents 图并消费 astream 事件，归一为前端友好的事件字典；
3. 多轮记忆：checkpointer 由应用启动流程注入（持久化实例见 app/main.py），
   thread_id 由用户 id + session_id 拼成，跨用户不串话。

本文件之外禁止 import deepagents。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.registry import ALL_TOOLS, build_args

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


# 单次提问允许的 LLM 调用次数上限（超过即终止执行，防止跑很久）
MODEL_CALL_LIMIT = 10

# 家庭助理系统提示词：中文回答 + 明确的工具选择策略（避免模型瞎猜或穷举调用）
SYSTEM_PROMPT = """你是「个人名册」家庭关系管理系统的助理，帮助家庭成员查看和维护人脉信息。

回答原则：
1. 一切涉及用户数据的问题（联系人、待办、往来、统计），必须先调用工具查询，禁止凭空编造或猜测。
2. 按问题选择合适的工具，能一步到位就不要多步：
   - 统计与名单类问题（"半年没联系的人""最近联系过谁"）→ get_stats（已含名单，一次即可）
   - 找某个人的信息 → search_contacts
   - 某人的交往记录 → get_contact_timeline
   - 临近的事 → get_upcoming_todos
3. 记待办/记活动等写入操作会先进入待确认队列，你需要告知用户"已生成提议，请在确认面板确认"。
4. 用简体中文回答，简洁口语化；数字与姓名必须来自工具结果，不得虚构。"""


class _SilentModel(BaseChatModel):
    """读历史专用的占位模型：建图需要一个 model 实例，但读 state 不会调用它。

    历史必须经图的 state 重建才拿得到（见 load_history），这里刻意不放真 LLM：
    看历史不该依赖「LLM 配置此刻是否还在」。
    """

    @property
    def _llm_type(self) -> str:
        """模型标识，仅用于日志与序列化。"""
        return "silent-placeholder"

    def _generate(self, *args, **kwargs):
        """占位模型永不参与推理；被调用说明用法错了。"""
        raise RuntimeError("历史读取不应触发模型调用")

    def bind_tools(self, tools, **kwargs):
        """图构造期会绑定工具，原样返回自身即可。"""
        return self


def _build_agent(model: BaseChatModel, tools: list, checkpointer: BaseCheckpointSaver):
    """构造 deepagents 图——对话与历史读取必须用同一套 channel 声明。

    deepagents 的唯一 import 点（D6.1）。
    """
    from deepagents import create_deep_agent
    from langchain.agents.middleware import ModelCallLimitMiddleware

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        middleware=[ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT, exit_behavior="end")],
    )


def _extract_text(content: Any) -> str:
    """兼容各家模型的 content 形态：纯字符串或分段列表。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return ""


def _make_langchain_tool(ai_tool, db: AsyncSession, user):
    """注册表工具 → langchain 工具（闭包持有当前请求的 db 会话与用户身份）。"""

    async def _invoke(**kwargs) -> str:
        tool_args = build_args(ai_tool, kwargs)
        return await ai_tool.run(db, user, tool_args)

    return StructuredTool.from_function(
        coroutine=_invoke,
        name=ai_tool.name,
        description=ai_tool.description,
        args_schema=ai_tool.args_schema,
    )


async def stream_agent(
    db: AsyncSession, user, llm, message: str, session_id: str,
    images: list[str] | None = None,
) -> AsyncIterator[dict]:
    """运行 agent 并产出归一事件流。

    事件形状：{"type":"text","delta":...} / {"type":"tool","name":...}。
    只透传主 agent（namespace 为空）的输出，子代理中间过程不上屏。
    单次提问的 LLM 调用上限 MODEL_CALL_LIMIT（官方 ModelCallLimitMiddleware，
    超限优雅结束，防止 agent 对一个问题反复绕圈跑很久）。
    """
    tools = [_make_langchain_tool(tool, db, user) for tool in ALL_TOOLS]
    agent = _build_agent(llm, tools, get_checkpointer())
    # thread_id 的拼装只发生在这里（业务侧只认 session_id）；带用户 id 避免跨用户串话
    config = {"configurable": {"thread_id": f"{user.id}:{session_id}"}}

    # 图片作为消息内容段直通模型（OpenAI 多模态格式）；带图时整体换 HumanMessage
    # 分段列表，纯文本维持字符串——对模型等价，但「带图」是视觉降级检测的明确信号。
    content: Any = message
    if images:
        content = [{"type": "text", "text": message}] + [
            {"type": "image_url", "image_url": {"url": uri}} for uri in images
        ]

    emitted_tools: set[str] = set()
    produced_text = False
    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=content)]},
        stream_mode=["messages"],
        subgraphs=True,
        config=config,
    ):
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

    if not produced_text:
        # 常见于触发调用上限被优雅终止：给用户一句可理解的收尾
        yield {
            "type": "text",
            "delta": f"（本次问题较复杂，已达单次执行上限 {MODEL_CALL_LIMIT} 次 LLM 调用，已停止。"
            "可以把问题拆小一点再问，或稍后重试。）",
        }


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

    不能直接读 checkpoint 的 channel_values：deepagents 把 messages 声明为
    DeltaChannel，那里只存增量写入，必须由图重建 state 才是完整消息列表。
    """
    config = {"configurable": {"thread_id": f"{user_id}:{session_id}"}}
    agent = _build_agent(_SilentModel(), [], get_checkpointer())
    snapshot = await agent.aget_state(config)
    if snapshot is None:
        return []
    return _to_history_messages(snapshot.values.get("messages"))


async def delete_history(session_id: str, user_id: int) -> None:
    """删除某会话在 checkpointer 里的全部数据（线程级清理）。"""
    checkpointer = get_checkpointer()
    await checkpointer.adelete_thread(f"{user_id}:{session_id}")
