"""MCP 个人令牌测试：签发/列表/吊销，以及 /mcp 门卫的令牌校验（D11）。"""

import hashlib
import json
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.db import get_session_factory
from app.modules.auth.models import User, UserToken
from tests.factories import login_as

pytestmark = pytest.mark.asyncio


async def _issue(client: AsyncClient, headers: dict, name: str = "Claude Desktop") -> dict:
    """经 API 签发一个令牌，返回响应体（含一次性明文）。"""
    response = await client.post("/api/v1/auth/tokens", json={"name": name}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _tokens_in_db() -> list[UserToken]:
    """直接读库：断言存储形态用（不经过 API）。"""
    async with get_session_factory()() as session:
        return list((await session.execute(select(UserToken))).scalars().all())


async def _call_gate(token: str) -> tuple[int, User | None]:
    """拿一个 Bearer 令牌打一次 /mcp 门卫，返回 (状态码, 门卫写入 contextvar 的用户)。"""
    from starlette.responses import JSONResponse

    from app.modules.ai.mcp_endpoint import AuthGate, mcp_current_user

    seen: dict = {}

    async def _probe(scope, receive, send):
        seen["user"] = mcp_current_user.get()
        await JSONResponse({"ok": True})(scope, receive, send)

    transport = ASGITransport(app=AuthGate(_probe))
    async with AsyncClient(transport=transport, base_url="http://mcp") as probe:
        response = await probe.post(
            "/mcp", headers={"Authorization": f"Bearer {token}"}
        )
    return response.status_code, seen.get("user")


async def test_issue_returns_plain_once_and_stores_hash(client, make_user):
    """签发响应给明文，库里只存 sha256（明文不落库）。"""
    user, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")

    body = await _issue(client, headers)

    assert body["token"].startswith("crm_")
    assert body["name"] == "Claude Desktop"
    rows = await _tokens_in_db()
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].token_hash == hashlib.sha256(body["token"].encode()).hexdigest()


async def test_list_never_exposes_secret(client, make_user):
    """列表只有用途名与时间，不含明文与哈希。"""
    await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")
    body = await _issue(client, headers)

    response = await client.get("/api/v1/auth/tokens", headers=headers)

    assert response.status_code == 200
    listing = response.json()
    assert [item["name"] for item in listing] == ["Claude Desktop"]
    assert "token" not in listing[0] and "token_hash" not in listing[0]
    assert body["token"] not in json.dumps(listing)


async def test_revoke_other_users_token_is_404(client, make_user):
    """吊销别人的令牌必须 404（同家庭也不行，令牌是账号私产）。"""
    owner, _ = await make_user(username="owner", password="pw12345678")
    await make_user(username="other", password="pw12345678", family_id=owner.family_id)
    owner_headers = await login_as(client, "owner", "pw12345678")
    other_headers = await login_as(client, "other", "pw12345678")
    token_id = (await _issue(client, owner_headers, name="他的令牌"))["id"]

    response = await client.delete(f"/api/v1/auth/tokens/{token_id}", headers=other_headers)

    assert response.status_code == 404


async def test_revoke_hides_from_list_and_kills_token(client, make_user):
    """吊销后：列表里消失，且该明文再也过不了门卫。"""
    await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")
    body = await _issue(client, headers)
    assert (await _call_gate(body["token"]))[0] == 200

    response = await client.delete(f"/api/v1/auth/tokens/{body['id']}", headers=headers)

    assert response.status_code == 204
    assert (await client.get("/api/v1/auth/tokens", headers=headers)).json() == []
    assert (await _call_gate(body["token"]))[0] == 401


async def test_mcp_gate_accepts_personal_token(client, make_user):
    """门卫认个人令牌，并把对应用户写进 contextvar（工具以该身份执行，D7）。"""
    user, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")
    body = await _issue(client, headers)

    status, gate_user = await _call_gate(body["token"])

    assert status == 200
    assert gate_user is not None and gate_user.id == user.id


async def test_mcp_gate_refreshes_last_used_at(client, make_user):
    """用过的令牌要留下最后使用时间（用户据此判断哪个令牌还在生效）。"""
    await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")
    body = await _issue(client, headers)
    assert (await _tokens_in_db())[0].last_used_at is None

    await _call_gate(body["token"])

    used = (await _tokens_in_db())[0].last_used_at
    assert used is not None
    assert used.replace(tzinfo=UTC) <= datetime.now(UTC)


async def test_mcp_gate_still_accepts_jwt(client, make_user):
    """JWT 过渡路径不能因为上了个人令牌而失效（老客户端配置不能断）。"""
    user, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")
    jwt_token = headers["Authorization"].removeprefix("Bearer ")

    status, gate_user = await _call_gate(jwt_token)

    assert status == 200
    assert gate_user is not None and gate_user.id == user.id


async def test_mcp_gate_rejects_garbage_and_empty(client, make_user):
    """乱码令牌与缺令牌都 401。"""
    await make_user(username="demo")

    assert (await _call_gate("crm_not-a-real-token"))[0] == 401
    assert (await _call_gate(""))[0] == 401


async def test_token_rejected_after_user_deactivated(client, make_user):
    """账号停用后其个人令牌立刻失效。"""
    user, _ = await make_user(username="demo")
    headers = await login_as(client, "demo", "demo12345")
    body = await _issue(client, headers)

    async with get_session_factory()() as session:
        stored = await session.get(User, user.id)
        stored.is_active = False
        await session.commit()

    assert (await _call_gate(body["token"]))[0] == 401
