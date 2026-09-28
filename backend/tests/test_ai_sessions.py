"""会话索引的跨用户隔离红线测试：列表不含他人行、越权删除 404（Review Focus #1）。"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_delete_others_session_is_404(client, login_headers, make_user, db_session):
    """A 删不掉 B 的会话（Review Focus #1：越权删同样 404）。"""
    from app.modules.ai.models import AiSession

    owner, _ = await make_user(username="del_owner", password="pw12345678")
    await make_user(username="del_intruder", password="pw12345678")
    headers = await login_headers("del_intruder", "pw12345678")
    db_session.add(AiSession(session_id="owned-del", user_id=owner.id, title="他的对话"))
    await db_session.commit()

    response = await client.delete("/api/v1/ai/sessions/owned-del", headers=headers)

    assert response.status_code == 404


async def test_delete_own_session_is_204(client, login_headers, make_user, db_session):
    """B 删自己的会话返回 204，且索引行真实消失。"""
    from app.core.db import get_session_factory
    from app.modules.ai.models import AiSession

    user, _ = await make_user(username="del_self", password="pw12345678")
    headers = await login_headers("del_self", "pw12345678")
    db_session.add(AiSession(session_id="own-del", user_id=user.id, title="我的对话"))
    await db_session.commit()

    response = await client.delete("/api/v1/ai/sessions/own-del", headers=headers)

    assert response.status_code == 204
    factory = get_session_factory()
    async with factory() as session:
        assert await session.get(AiSession, "own-del") is None


async def test_session_list_isolates_users(client, login_headers, make_user, db_session):
    """A 的会话不出现在 B 的列表里（Review Focus #1 的列表维度）。"""
    from app.modules.ai.models import AiSession

    owner, _ = await make_user(username="list_owner", password="pw12345678")
    await make_user(username="list_other", password="pw12345678")
    other_headers = await login_headers("list_other", "pw12345678")
    db_session.add(AiSession(session_id="list-owned", user_id=owner.id, title="他的对话"))
    db_session.add(AiSession(session_id="list-shared", user_id=owner.id, title="他的另一场"))
    await db_session.commit()

    response = await client.get("/api/v1/ai/sessions", headers=other_headers)

    assert response.status_code == 200
    ids = [item["session_id"] for item in response.json()]
    assert "list-owned" not in ids and "list-shared" not in ids