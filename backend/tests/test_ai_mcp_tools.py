"""MCP 端点工具测试：外部 MCP 客户端路径也必须把提议提交落库。

现有测试全都直接调 tool.run() 或走内部 SSE，**没有任何用例经过 MCP 的
_dynamic_handler**——所以"handler 自建会话却从不 commit"这个 Critical 缺陷
才能潜伏至今（工具回执说"已生成提议（编号 N）"，库里其实什么都没有）。
"""

import pytest
from sqlalchemy import func, select

from app.core.db import get_session_factory
from app.modules.ai import mcp_endpoint
from app.modules.ai.models import PendingAction
from app.modules.ai.registry import get_tool
from tests.factories import create_contact_for

pytestmark = pytest.mark.asyncio


async def test_mcp_write_tool_commits_proposal(make_user):
    """MCP handler 调写工具后必须提交：否则回执是假的，确认面板永远看不到这条提议。

    断言必须用**另一次全新会话**去查——同一会话里查得到未提交行，
    根本证明不了提交发生过（未提交事务随 async with 退出即回滚）。
    """
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")

    tool = get_tool("create_task")
    handler = mcp_endpoint._dynamic_handler(tool)
    # 身份经 contextvar 注入，与 AuthGate 门卫层的真实路径一致
    token = mcp_endpoint.mcp_current_user.set(demo)
    try:
        out = await handler(title="给唐琴打电话", contact_id=contact.id)
    finally:
        mcp_endpoint.mcp_current_user.reset(token)

    assert "待确认" in out

    factory = get_session_factory()
    async with factory() as fresh:
        count = (
            await fresh.execute(select(func.count()).select_from(PendingAction))
        ).scalar()
    assert count == 1
