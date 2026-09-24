"""geo 模块共享类型：地理编码结果契约。"""

from dataclasses import dataclass


@dataclass
class GeoResult:
    """地理编码结果：坐标 + 精度级别 + 来源（amap / static）+ 所属省级名称。"""

    lng: float
    lat: float
    level: str
    source: str
    province: str | None = None
