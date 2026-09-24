"""AI 配置接口测试：读写回显（密钥掩码）、状态联动、连接测试失败透传。"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_ai_config_roundtrip(client, make_user, login_headers):
    """保存 → 回显（密钥掩码）→ 状态转已配置。"""
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    before = (await client.get("/api/v1/settings/ai", headers=headers)).json()
    assert before["configured"] is False

    saved = await client.put(
        "/api/v1/settings/ai",
        json={
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-very-secret-key-123456",
            "model": "glm-4.7",
        },
        headers=headers,
    )
    assert saved.status_code == 200 and saved.json()["configured"] is True

    shown = (await client.get("/api/v1/settings/ai", headers=headers)).json()
    assert shown["configured"] is True
    assert shown["base_url"] == "https://api.example.com/v1"
    assert shown["model"] == "glm-4.7"
    assert "very-secret" not in shown["api_key_masked"]
    assert shown["api_key_masked"].startswith("sk-v") or shown["api_key_masked"].startswith("sk-")

    status = (await client.get("/api/v1/settings/ai-status", headers=headers)).json()
    assert status["configured"] is True


async def test_ai_config_validation(client, make_user, login_headers):
    """保存校验：缺字段 → 422。"""
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    bad = await client.put(
        "/api/v1/settings/ai",
        json={"base_url": "https://x", "model": "m"},
        headers=headers,
    )
    assert bad.status_code == 422


async def test_ai_connection_test_reports_failure(client, make_user, login_headers):
    """连接测试：不可达端点返回 ok=False 与失败信息（不抛 500）。"""
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    result = await client.post(
        "/api/v1/settings/ai/test",
        json={
            "base_url": "http://127.0.0.1:9/v1",
            "api_key": "sk-test",
            "model": "whatever",
        },
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["ok"] is False
    assert "连接失败" in result.json()["message"]
