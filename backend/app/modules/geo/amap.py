"""高德地理编码 provider：地址文本 → 坐标（/v3/geocode/geo，D14）。

只在 settings 配置了 key 时由调用方启用；网络/服务故障向上抛错，
由 geocoder 编排层统一捕获并降级到静态表。
"""

import httpx

from app.modules.geo.types import GeoResult

_AMAP_GEO_URL = "https://restapi.amap.com/v3/geocode/geo"
# 外部调用必须限时：地理编码是保存联系人的同步旁路，不能拖垮请求
_TIMEOUT_SECONDS = 3.0

# 高德返回的 level 值 → 本系统精度级别；表外的原样保留
_LEVEL_MAP = {"省": "province", "市": "city", "区县": "district"}


async def resolve_amap(text: str, key: str) -> GeoResult | None:
    """调用高德地理编码接口解析文本；未命中返回 None，故障抛错（编排层降级）。

    参数 text 为原始位置文本（如"上海市浦东新区"），key 为高德 Web 服务 key。
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.get(_AMAP_GEO_URL, params={"key": key, "address": cleaned})
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("status") != "1" or not payload.get("geocodes"):
        return None
    geocode = payload["geocodes"][0]
    lng_text, _, lat_text = geocode.get("location", "").partition(",")
    try:
        lng, lat = float(lng_text), float(lat_text)
    except ValueError:
        return None
    level = _LEVEL_MAP.get(geocode.get("level", ""), geocode.get("level", "unknown"))
    raw_province = geocode.get("province")
    province = raw_province if isinstance(raw_province, str) and raw_province else None
    return GeoResult(
        lng=lng, lat=lat, level=level, source="amap", province=province
    )
