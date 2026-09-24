"""历法引擎测试：公历/农历周年日的下次发生日计算与中文显示（纯函数，不涉 DB）。"""

from datetime import date

import pytest
from lunar_python import Lunar

from app.modules.contacts.calendar import (
    lunar_display_name,
    next_lunar_occurrence,
    next_solar_occurrence,
)

pytestmark = pytest.mark.asyncio


def _lunar_date(year: int, month: int, day: int, leap: bool = False) -> date:
    """用 lunar-python 构造测试期望值（被测的是封装逻辑，期望值来自库本身）。"""
    lunar = Lunar.fromYmd(year, -month if leap else month, day)
    return date.fromisoformat(lunar.getSolar().toYmd())


class TestSolarOccurrence:
    """公历周年日：今年未过用今年，已过滚明年，当天即今天。"""

    def test_past_rolls_to_next_year(self):
        """今年的月日已过 → 滚到明年（生日例子：过期不惩罚，滚下一年）。"""
        assert next_solar_occurrence(date(1958, 5, 12), date(2026, 9, 21)) == date(2027, 5, 12)

    def test_upcoming_this_year(self):
        """今年的月日还没到 → 取今年。"""
        assert next_solar_occurrence(date(10, 10, 3), date(2026, 9, 21)) == date(2026, 10, 3)

    def test_today_returns_today(self):
        """恰好今天 → 今天（当天提醒，不是明年）。"""
        assert next_solar_occurrence(date(1980, 9, 21), date(2026, 9, 21)) == date(2026, 9, 21)

    def test_feb29_falls_back_to_feb28_in_plain_years(self):
        """2-29 生日在平年回落 2-28（每年都过，民间习惯），闰年用真 2-29。"""
        assert next_solar_occurrence(date(2000, 2, 29), date(2026, 3, 1)) == date(2027, 2, 28)
        assert next_solar_occurrence(date(2000, 2, 29), date(2027, 3, 1)) == date(2028, 2, 29)


class TestLunarOccurrence:
    """农历周年日：换算公历、跨年滚动、闰月回落。"""

    def test_normal_month_day_rolls_to_next_year(self):
        """农历三月初三（今年已过）→ 明年农历三月初三对应的公历。"""
        assert next_lunar_occurrence(3, 3, False, date(2026, 9, 21)) == _lunar_date(2027, 3, 3)

    def test_upcoming_this_year(self):
        """今年农历日期还没到 → 今年。"""
        assert next_lunar_occurrence(12, 23, False, date(2026, 9, 21)) == _lunar_date(2026, 12, 23)

    def test_leap_month_falls_back_to_plain_month_when_missing(self):
        """闰三月生日但 2026 无闰三月 → 回落平月三月初三（不抛异常）。"""
        assert next_lunar_occurrence(3, 3, True, date(2026, 1, 1)) == _lunar_date(2026, 3, 3)

    def test_leap_month_used_when_present(self):
        """2025 有闰六月 → 闰六月初三用闰月。"""
        expected = _lunar_date(2025, 6, 3, leap=True)
        assert next_lunar_occurrence(6, 3, True, date(2025, 1, 1)) == expected

    def test_lunar_new_year_boundary(self):
        """农历日期在公历年初（正月初一）跨年滚动正确。"""
        assert next_lunar_occurrence(1, 1, False, date(2026, 12, 1)) == _lunar_date(2027, 1, 1)


class TestLunarDisplay:
    """农历中文显示：用于待办/详情页的"三月初三"样式。"""

    def test_display_name(self):
        assert lunar_display_name(3, 3, False) == "农历三月初三"

    def test_display_name_leap(self):
        assert lunar_display_name(6, 3, True) == "农历闰六月初三"

    def test_display_name_twelfth_month(self):
        """十二月显示为腊月。"""
        assert lunar_display_name(12, 1, False) == "农历腊月初一"
