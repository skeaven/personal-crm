"""settings 高德 key 配置端点测试（D14）：掩码回显、保存、连接测试。"""

import pytest

from app.modules.settings.service import KEY_GEO_AMAP, get_setting_value

pytestmark = pytest.mark.asyncio


async def test_amap_config_roundtrip_masked(client, make_user, login_headers, db_session):
    """保存后回显掩码；落库存的是明文（供地理编码调用）。"""
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    resp = await client.get("/api/v1/settings/geo/amap", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["configured"] is False

    save = await client.put(
        "/api/v1/settings/geo/amap", json={"api_key": "abcd1234efgh5678"}, headers=headers
    )
    assert save.status_code == 200
    assert save.json()["configured"] is True

    echo = await client.get("/api/v1/settings/geo/amap", headers=headers)
    body = echo.json()
    assert body["configured"] is True
    assert body["api_key_masked"] == "abcd****5678"
    stored = await get_setting_value(db_session, KEY_GEO_AMAP)
    assert stored == {"api_key": "abcd1234efgh5678"}


async def test_amap_test_endpoint(client, make_user, login_headers, monkeypatch):
    """连接测试：成功回显解析结果；失败透传原因。"""
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    async def ok_amap(text, key):
        from app.modules.geo.types import GeoResult

        return GeoResult(lng=116.4, lat=39.9, level="city", source="amap")

    async def bad_amap(text, key):
        raise RuntimeError("invalid key")

    monkeypatch.setattr("app.modules.geo.amap.resolve_amap", ok_amap)
    ok = await client.post(
        "/api/v1/settings/geo/amap/test", json={"api_key": "good"}, headers=headers
    )
    assert ok.json()["ok"] is True
    assert "116.4000" in ok.json()["message"]

    monkeypatch.setattr("app.modules.geo.amap.resolve_amap", bad_amap)
    bad = await client.post(
        "/api/v1/settings/geo/amap/test", json={"api_key": "wrong"}, headers=headers
    )
    assert bad.json()["ok"] is False
    assert "invalid key" in bad.json()["message"]
