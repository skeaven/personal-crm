"""地理编码编排：provider 链 = 高德（配置了 key）→ 静态表兜底（D14）。

本模块是 geo 对外的唯一入口；调用方（contacts 保存流程）注入 amap_key，
本模块不做 settings 读取（依赖方向：contacts → geo，geo → core）。
"""

from app.modules.geo.amap import resolve_amap
from app.modules.geo.static_table import resolve_static
from app.modules.geo.types import GeoResult


async def resolve_location(text: str, *, amap_key: str | None = None) -> GeoResult | None:
    """把位置文本解析为坐标；全链未命中返回 None，不抛错。

    链路：配置了 key 先走高德（区县级精度），高德未命中或调用异常
    （网络/配额/服务故障）时静默降级静态表——外部服务的可用性不应
    阻塞联系人保存。
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    if amap_key:
        try:
            amap_result = await resolve_amap(cleaned, amap_key)
        except Exception:  # noqa: BLE001 — 高德任何故障都降级，不上抛
            amap_result = None
        if amap_result is not None:
            return amap_result
    return resolve_static(cleaned)
