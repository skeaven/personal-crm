"""历法引擎：公历/农历周年日的下次发生日计算（contacts 模块的唯一口径，纯函数）。

D8 决策：农历换算统一走 lunar-python；闰月生日在无闰月年份回落平月同日（民间习惯）。
所有函数接受 today 注入，保证可测试性与调用方（dashboard 聚合）的口径一致。
"""

from datetime import date

from lunar_python import Lunar, LunarYear


def next_solar_occurrence(birthday: date, today: date) -> date:
    """计算公历周年日的下次发生日（含当天）。

    2-29 在平年目标回落 2-28：生日本质是"那一天想着他"，民间习惯不过分苛求历法。
    """
    month, day = birthday.month, birthday.day
    for year in (today.year, today.year + 1):
        candidate = _safe_date(year, month, day)
        if candidate >= today:
            return candidate
    # 理论不可达（明年必然 >= today），防御性返回明年月末
    return date(today.year + 1, 12, 31)


def next_lunar_occurrence(
    lunar_month: int, lunar_day: int, lunar_is_leap: bool, today: date
) -> date:
    """计算农历周年日的下次发生日（含当天），换算为公历返回。

    闰月处理：lunar_is_leap=True 时优先找带闰月的年份；无闰月年份回落平月同日。
    """
    for year in (today.year, today.year + 1, today.year + 2):
        candidate = _lunar_to_solar(year, lunar_month, lunar_day, lunar_is_leap)
        if candidate >= today:
            return candidate
    return date(today.year + 3, 12, 31)  # 防御性兜底，正常不可达


def lunar_display_name(lunar_month: int, lunar_day: int, lunar_is_leap: bool) -> str:
    """农历日期的中文展示名，如"农历三月初三"、"农历闰六月初三"。"""
    leap_prefix = "闰" if lunar_is_leap else ""
    month_name = _LUNAR_MONTH_NAMES[lunar_month]
    day_name = _lunar_day_name(lunar_day)
    return f"农历{leap_prefix}{month_name}月{day_name}"


def _safe_date(year: int, month: int, day: int) -> date:
    """构造公历日期；2-29 在平年回落 2-28，其余非法日回落到当月最后一天。"""
    for offset in range(day, 0, -1):
        try:
            return date(year, month, offset)
        except ValueError:
            continue
    raise ValueError(f"无法构造日期: {year}-{month}-{day}")


def _lunar_to_solar(year: int, month: int, day: int, is_leap: bool) -> date:
    """农历 (年, 月, 日) → 公历 date；目标年无对应闰月时回落平月。"""
    leap_month = LunarYear.fromYear(year).getLeapMonth()
    if is_leap and leap_month != month:
        is_leap = False  # 该年没有这个闰月，按民间习惯用平月
    lunar = Lunar.fromYmd(year, -month if is_leap else month, day)
    return date.fromisoformat(lunar.getSolar().toYmd())


_LUNAR_MONTH_NAMES = {
    1: "正", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
    7: "七", 8: "八", 9: "九", 10: "十", 11: "冬", 12: "腊",
}


_ONES = "一二三四五六七八九"


def _lunar_day_name(day: int) -> str:
    """农历日的中文表示：初一~初十、十一~十九、二十、廿一~廿九、三十。"""
    if day == 10:
        return "初十"
    if day == 20:
        return "二十"
    if day == 30:
        return "三十"
    tens, ones = divmod(day, 10)
    ones_name = _ONES[ones - 1]
    tens_name = ("初", "十", "廿")[tens]
    return f"{tens_name}{ones_name}"
