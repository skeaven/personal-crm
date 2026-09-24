"""静态坐标表：内置省/市/直辖市辖区中心点数据（DataV.GeoAtlas 开放数据整理）。

零配置、离线可用的兜底 provider；精度为市区级，输入含省/市名时按最长匹配 +
父级命中打分取最精确的一条。
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.modules.geo.types import GeoResult

_DATA_PATH = Path(__file__).parent / "data" / "cities.json"

# 行政区划通名后缀：匹配时从条目名剥掉最长的一个，让"杭州"能命中"杭州市"。
# 顺序即优先级（长者先判），保证"自治区"先于"区"被剥。
_ADMIN_SUFFIXES = ("特别行政区", "自治区", "自治州", "地区", "盟", "省", "市", "区", "县", "旗")


@dataclass
class _TableEntry:
    """静态表一行：名称、父级（用于 qualified 加分）、坐标、行政级别。"""

    name: str
    core: str  # 剥掉通名后缀的短名（"杭州市"→"杭州"），支持无后缀输入
    parent: str
    parent_core: str
    lng: float
    lat: float
    level: str


def _strip_suffix(name: str) -> str:
    """剥掉行政区划通名后缀（最长优先，只剥一趟），得到可子串匹配的短名。

    "杭州市"→"杭州"、"广西壮族自治区"→"广西壮族"；剥空时保留原名兜底。
    """
    for suffix in _ADMIN_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


@lru_cache(maxsize=1)
def _load_table() -> list[_TableEntry]:
    """装载 cities.json 为条目列表（进程内缓存一次；纯只读，量级 ~500 行）。"""
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return [
        _TableEntry(
            name=item["name"],
            core=_strip_suffix(item["name"]),
            parent=item.get("parent", ""),
            parent_core=_strip_suffix(item.get("parent", "")),
            lng=item["lng"],
            lat=item["lat"],
            level=item["level"],
        )
        for item in raw
    ]


def resolve_static(text: str) -> GeoResult | None:
    """在静态表中解析位置文本；命中返回坐标，未命中返回 None。

    匹配规则：条目名或短名出现在输入中即为候选；得分 = 命中长度 +
    （父级名也出现在输入中 +1，用于"浙江省杭州市"选市而非省）。
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    best: _TableEntry | None = None
    best_score = 0
    for entry in _load_table():
        score = 0
        if entry.name in cleaned:
            score = len(entry.name)
        elif entry.core in cleaned:
            score = len(entry.core) - 0.5  # 无后缀匹配略降权，优先全名命中
        if score <= 0:
            continue
        if entry.parent and entry.parent in cleaned:
            score += 1  # 输入里点名了父级（省/直辖市），锁定该条目
        elif entry.parent_core and entry.parent_core in cleaned:
            score += 1
        if score > best_score:
            best, best_score = entry, score
    if best is None:
        return None
    # 省级条目自身即省份；市/辖区取父级（直辖市辖区的 parent 即直辖市名）
    province = best.name if best.level == "province" else (best.parent or None)
    return GeoResult(
        lng=best.lng, lat=best.lat, level=best.level, source="static", province=province
    )
