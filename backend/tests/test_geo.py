"""geo 模块测试：静态表解析、高德 provider 链、降级契约（D14）。"""

import pytest

from app.modules.geo import geocoder

pytestmark = pytest.mark.asyncio


async def test_static_resolves_municipality_district():
    """直辖市辖区命中静态表：返回坐标且来源为 static。"""
    result = await geocoder.resolve_location("上海市浦东新区", amap_key=None)
    assert result is not None
    assert result.source == "static"
    assert 121.0 < result.lng < 122.5
    assert 30.5 < result.lat < 32.0


async def test_static_resolves_city_with_and_without_suffix():
    """地级市去后缀匹配：'杭州市'与'杭州'都能命中。"""
    for text in ("浙江省杭州市", "杭州"):
        result = await geocoder.resolve_location(text, amap_key=None)
        assert result is not None, text
        assert result.source == "static"
        assert 119.0 < result.lng < 121.0
        assert 29.0 < result.lat < 31.0


async def test_static_resolves_province():
    """省名直接命中（精度为省会坐标）。"""
    result = await geocoder.resolve_location("四川省", amap_key=None)
    assert result is not None
    assert result.source == "static"
    assert result.level == "province"


async def test_unknown_text_returns_none():
    """无法匹配的文本返回 None，不抛错。"""
    assert await geocoder.resolve_location("不存在的地方xyz", amap_key=None) is None
    assert await geocoder.resolve_location("   ", amap_key=None) is None
    assert await geocoder.resolve_location("", amap_key=None) is None


async def test_amap_wins_when_configured(monkeypatch):
    """配置了 key 且解析成功：返回 amap 结果（更精确），不落静态表。"""
    async def fake_amap(text, key):
        return geocoder.GeoResult(lng=121.4737, lat=31.2304, level="district", source="amap")

    monkeypatch.setattr(geocoder, "resolve_amap", fake_amap)
    result = await geocoder.resolve_location("上海市黄浦区", amap_key="test-key")
    assert result is not None
    assert result.source == "amap"


async def test_amap_none_falls_back_to_static(monkeypatch):
    """高德未命中（返回 None）：静默降级静态表。"""
    async def fake_amap(text, key):
        return None

    monkeypatch.setattr(geocoder, "resolve_amap", fake_amap)
    result = await geocoder.resolve_location("杭州市", amap_key="test-key")
    assert result is not None
    assert result.source == "static"


async def test_amap_error_falls_back_to_static(monkeypatch):
    """高德调用异常（网络/服务故障）：静默降级静态表，不向上抛错。"""
    async def broken_amap(text, key):
        raise RuntimeError("network down")

    monkeypatch.setattr(geocoder, "resolve_amap", broken_amap)
    result = await geocoder.resolve_location("北京市", amap_key="test-key")
    assert result is not None
    assert result.source == "static"
