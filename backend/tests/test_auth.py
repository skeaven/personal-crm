"""认证模块测试：登录成功/失败与登录态校验。"""

import pytest
from httpx import AsyncClient

from tests.factories import login_as


@pytest.fixture
async def demo_user(make_user):
    """预置一个演示用户，返回 (User, 明文密码)。"""
    user, password = await make_user(username="demo", display_name="阿澄")
    return user, password


async def test_login_success(client: AsyncClient, demo_user):
    """正确账号密码返回令牌与用户信息。"""
    user, _ = demo_user
    response = await client.post(
        "/api/v1/auth/login", json={"username": "demo", "password": "demo12345"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["username"] == "demo"
    assert body["user"]["family_id"] == user.family_id


async def test_login_wrong_password(client: AsyncClient, demo_user):
    """密码错误统一 401，不暴露原因。"""
    response = await client.post(
        "/api/v1/auth/login", json={"username": "demo", "password": "wrong"}
    )
    assert response.status_code == 401


async def test_me_requires_token(client: AsyncClient, demo_user):
    """无令牌访问 /me 返回 401。"""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_with_token(client: AsyncClient, demo_user):
    """有效令牌返回当前用户信息。"""
    headers = await login_as(client, "demo", "demo12345")
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "demo"
