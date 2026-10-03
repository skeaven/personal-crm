"""dashboard 聚合测试：待办四桶（待办/过期/已完成/全部）× 五来源（任务/心愿/还款/活动/生日）。

数据全部相对"当天"动态构造（正午 UTC，东八区转本地仍为同一天），任何日期运行都稳定。
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from tests.factories import (
    create_activity_for,
    create_contact_for,
    create_date_for,
    create_family_user,
    create_fund_for,
    create_task_for,
    create_wishlist_for,
)

pytestmark = pytest.mark.asyncio

_TODAY = date.today()
# 正午 UTC 构造：转本地（东八区）仍是同一天，保证 days_left 断言无 off-by-one
_NOON_UTC = datetime.combine(_TODAY, time(12, 0), tzinfo=UTC)


def _days_ahead_date(days: int) -> date:
    """相对当天的日期（测试数据构造用）。"""
    return _TODAY + timedelta(days=days)


def _days_ahead_dt(days: int) -> datetime:
    """相对当天的时刻（活动/任务时间字段用）。"""
    return _NOON_UTC + timedelta(days=days)


async def _board(client, headers, bucket: str):
    """调用聚合接口并返回 TodoItem 列表。"""
    resp = await client.get(f"/api/v1/dashboard/todos?bucket={bucket}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(items: list[dict]) -> set[tuple[str, str]]:
    """取 (source, title) 集合，方便断言来源与内容。"""
    return {(item["source"], item["title"]) for item in items}


async def test_task_split_by_due(client, make_user, login_headers):
    """任务按截止日分桶：未到期→待办，已过期→过期页签，done→已完成，all 取并集。"""
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    await create_task_for(demo, title="未来任务", due_at=_days_ahead_dt(5))
    await create_task_for(demo, title="过期任务", due_at=_days_ahead_dt(-3))
    await create_task_for(demo, title="完成任务", status="done")

    todo = _ids(await _board(client, headers, "todo"))
    assert ("task", "未来任务") in todo and ("task", "过期任务") not in todo

    overdue = _ids(await _board(client, headers, "overdue"))
    assert ("task", "过期任务") in overdue and ("task", "未来任务") not in overdue

    done = _ids(await _board(client, headers, "done"))
    assert ("task", "完成任务") in done

    everything = _ids(await _board(client, headers, "all"))
    assert everything == todo | overdue | done


async def test_task_without_due_stays_in_todo(client, make_user, login_headers):
    """无截止日的任务永远算待办，不过期。"""
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    await create_task_for(demo, title="某天要做的杂事", due_at=None)

    todo = _ids(await _board(client, headers, "todo"))
    assert ("task", "某天要做的杂事") in todo
    assert not _ids(await _board(client, headers, "overdue"))


async def test_wish_target_date_and_given(client, make_user, login_headers):
    """愿望：定了送出日的 想送 项进入待办；已送出的进入已完成。"""
    demo, _ = await make_user(username="demo")
    mother = await create_contact_for(demo, name="陈秀兰", nickname="老妈")
    headers = await login_headers("demo", "demo12345")
    await create_wishlist_for(
        demo, contact_id=mother.id, title="血压仪", status="open",
        target_date=_days_ahead_date(10),
    )
    await create_wishlist_for(demo, title="旧愿望", status="given")

    todo = await _board(client, headers, "todo")
    wish = [item for item in todo if item["source"] == "wish"]
    assert len(wish) == 1
    assert wish[0]["title"] == "血压仪"
    assert wish[0]["contact_name"] == "老妈"
    assert wish[0]["days_left"] == 10

    done = _ids(await _board(client, headers, "done"))
    assert ("wish", "旧愿望") in done


async def test_repayment_pending_and_overdue(client, make_user, login_headers):
    """还款提醒：未结清借款按应还日分桶，含应还日与结清状态。"""
    demo, _ = await make_user(username="demo")
    friend = await create_contact_for(demo, name="李娜")
    headers = await login_headers("demo", "demo12345")
    await create_fund_for(
        demo, contact_id=friend.id, direction="out", category="loan", amount=2000,
        occurred_at=_days_ahead_date(-30), due_at=_days_ahead_date(-2), status="pending",
    )
    await create_fund_for(
        demo, contact_id=friend.id, direction="in", category="repayment", amount=1000,
        occurred_at=_days_ahead_date(-15), due_at=_days_ahead_date(-15), status="settled",
    )

    overdue = await _board(client, headers, "overdue")
    loan = [item for item in overdue if item["source"] == "repayment"]
    assert len(loan) == 1 and loan[0]["days_left"] == -2

    done = _ids(await _board(client, headers, "done"))
    assert any(source == "repayment" for source, _ in done)


async def test_activity_future_only(client, make_user, login_headers):
    """活动：未来的进入待办；已发生的活动是历史，不进任何待办桶。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国", nickname="老爸")
    headers = await login_headers("demo", "demo12345")
    await create_activity_for(
        demo, title="周末家宴", occurred_at=_days_ahead_dt(4),
        participant_contact_ids=[father.id],
    )
    await create_activity_for(demo, title="过去的聚会", occurred_at=_days_ahead_dt(-20))

    todo = await _board(client, headers, "todo")
    activities = [item for item in todo if item["source"] == "activity"]
    assert len(activities) == 1 and activities[0]["title"].startswith("周末家宴")
    assert activities[0]["days_left"] == 4
    assert not [item for item in todo if item["title"].startswith("过去的聚会")]


async def test_birthday_window_and_lead_days(client, make_user, login_headers):
    """生日：进入 提前量 窗口才出现；无提前量默认 7 天；过期自动滚明年不进过期桶。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国", nickname="老爸")
    mother = await create_contact_for(demo, name="陈秀兰", nickname="老妈")
    headers = await login_headers("demo", "demo12345")

    # 老爸：3 天后生日，提前 [7,1] → 出现，days_left=3
    await create_date_for(
        demo, contact_id=father.id, type="birthday", calendar="solar",
        date_solar=_days_ahead_date(3), reminder_lead_days=[7, 1],
    )
    # 老妈：30 天后生日，提前 [7,1] → 窗口外不出现
    await create_date_for(
        demo, contact_id=mother.id, type="birthday", calendar="solar",
        date_solar=_days_ahead_date(30), reminder_lead_days=[7, 1],
    )

    todo = await _board(client, headers, "todo")
    birthdays = [item for item in todo if item["source"] == "birthday"]
    assert [item["title"] for item in birthdays] == ["老爸的生日"]
    assert birthdays[0]["days_left"] == 3
    # 生日永不进过期桶
    overdue_sources = {item["source"] for item in await _board(client, headers, "overdue")}
    assert "birthday" not in overdue_sources


async def test_lunar_birthday_with_display_label(client, make_user, login_headers):
    """农历生日：下次发生日进窗口时出现，并带农历中文标签（如 农历三月初三）。"""
    demo, _ = await make_user(username="demo")
    mother = await create_contact_for(demo, name="陈秀兰", nickname="老妈")
    headers = await login_headers("demo", "demo12345")

    # today+3 对应的农历月日 → 下次发生恰为 today+3，稳定落在窗口内
    from lunar_python import Solar

    target = _days_ahead_date(3)
    lunar = Solar.fromYmd(target.year, target.month, target.day).getLunar()
    lunar_month = abs(lunar.getMonth())
    # 用平月构造（闰日情形退化为平月，窗口判定行为一致）
    await create_date_for(
        demo, contact_id=mother.id, type="birthday", calendar="lunar",
        lunar_month=lunar_month, lunar_day=lunar.getDay(),
        lunar_is_leap=False, reminder_lead_days=[7],
    )

    todo = await _board(client, headers, "todo")
    birthdays = [item for item in todo if item["source"] == "birthday"]
    assert len(birthdays) == 1 and birthdays[0]["days_left"] == 3
    assert birthdays[0]["lunar_label"] is not None
    assert birthdays[0]["lunar_label"].startswith("农历")


async def test_dashboard_visibility_isolation(client, make_user, login_headers):
    """D7 隔离：成员的聚合视图不含他人的私密待办。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    await create_task_for(demo, title="私密任务", visibility="private", due_at=_days_ahead_dt(2))
    await create_task_for(demo, title="家庭任务", visibility="family", due_at=_days_ahead_dt(2))
    tong_headers = await login_headers("tong", "demo12345")

    todo = _ids(await _board(client, tong_headers, "todo"))
    assert todo == {("task", "家庭任务")}
