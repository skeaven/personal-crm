"""dashboard 聚合测试补充：联系人详情页时间线（三源归并 + 游标分页 + 可见性）。"""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from tests.factories import (
    create_activity_for,
    create_contact_for,
    create_family_user,
    create_fund_for,
    create_gift_for,
)

pytestmark = pytest.mark.asyncio

_TODAY = date(2026, 9, 21)


def _d(days_ago: int) -> date:
    """相对今天的日期（days_ago 天前）。"""
    return _TODAY - timedelta(days=days_ago)


def _dt(days_ago: int) -> datetime:
    """相对今天的时刻（正午 UTC，转本地仍同一天）。"""
    return datetime.combine(_d(days_ago), time(12, 0), tzinfo=UTC)


async def _timeline(client, headers, contact_id: int):
    """调用时间线接口（全量返回，无分页参数），返回响应 JSON。"""
    resp = await client.get(
        f"/api/v1/contacts/{contact_id}/timeline", headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_timeline_aggregates_three_sources(client, make_user, login_headers):
    """三源聚合：礼物、资金、活动（按参与者）都出现在同一个人的时间线上。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国", nickname="老爸")
    headers = await login_headers("demo", "demo12345")

    await create_gift_for(
        demo, contact_id=father.id, direction="given",
        title="按摩仪", amount="599.00", given_at=_d(10),
    )
    await create_fund_for(
        demo, contact_id=father.id, direction="out", category="gift_money",
        amount="800", occurred_at=_d(5), description="婚礼随礼",
    )
    await create_activity_for(
        demo, title="家庭聚餐", occurred_at=_dt(2), participant_contact_ids=[father.id],
    )

    page = await _timeline(client, headers, father.id)
    sources = {item["source"] for item in page["items"]}
    assert sources == {"gift", "fund", "activity"}


async def test_timeline_desc_order(client, make_user, login_headers):
    """时间倒序：最近发生在前。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    headers = await login_headers("demo", "demo12345")

    await create_gift_for(
        demo, contact_id=father.id, direction="given", title="旧礼物", given_at=_d(30)
    )
    await create_fund_for(
        demo, contact_id=father.id, direction="in", category="repayment",
        amount="100", occurred_at=_d(3),
    )
    await create_activity_for(
        demo, title="最近的家宴", occurred_at=_dt(1), participant_contact_ids=[father.id]
    )

    page = await _timeline(client, headers, father.id)
    titles = [item["title"] for item in page["items"]]
    assert titles == ["最近的家宴", "还款", "旧礼物"]


async def test_timeline_full_load_no_pagination(client, make_user, login_headers):
    """全量语义：5 条记录一次返回、倒序完整，不分页截断。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    headers = await login_headers("demo", "demo12345")

    for offset, days in enumerate([9, 7, 5, 3, 1]):
        await create_gift_for(
            demo, contact_id=father.id, direction="given",
            title=f"礼物{offset + 1}", given_at=_d(days),
        )

    page = await _timeline(client, headers, father.id)
    titles = [item["title"] for item in page["items"]]
    assert titles == [f"礼物{i}" for i in range(5, 0, -1)]


async def test_timeline_excludes_other_contacts(client, make_user, login_headers):
    """别人的记录不串台：挂在其他联系人下的礼物不出现。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    mother = await create_contact_for(demo, name="陈秀兰")
    headers = await login_headers("demo", "demo12345")

    await create_gift_for(
        demo, contact_id=mother.id, direction="given", title="给妈妈的", given_at=_d(1)
    )
    await create_gift_for(
        demo, contact_id=father.id, direction="given", title="给爸爸的", given_at=_d(2)
    )

    page = await _timeline(client, headers, father.id)
    assert [item["title"] for item in page["items"]] == ["给爸爸的"]


async def test_timeline_activity_by_participation(client, make_user, login_headers):
    """活动按参与者关联：参加者有此活动，未参加者没有。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    mother = await create_contact_for(demo, name="陈秀兰")
    headers = await login_headers("demo", "demo12345")

    await create_activity_for(
        demo, title="只有爸妈的聚餐", occurred_at=_dt(2),
        participant_contact_ids=[father.id, mother.id],
    )
    other = await create_contact_for(demo, name="张伟")
    await create_activity_for(
        demo, title="球局", occurred_at=_dt(1), participant_contact_ids=[other.id],
    )

    page = await _timeline(client, headers, father.id)
    assert [item["title"] for item in page["items"]] == ["只有爸妈的聚餐"]


async def test_timeline_visibility_isolation(client, make_user, login_headers):
    """D7：私密的礼物流水对家庭成员不可见。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    father = await create_contact_for(demo, name="陈建国", visibility="family")
    await create_gift_for(
        demo, contact_id=father.id, direction="given", title="私下的礼物",
        given_at=_d(1), visibility="private",
    )
    tong_headers = await login_headers("tong", "demo12345")

    page = await _timeline(client, tong_headers, father.id)
    assert page["items"] == []


async def test_timeline_unreadable_contact_404(client, make_user, login_headers):
    """不可读联系人的时间线按 404 处理。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    private = await create_contact_for(demo, name="周明", visibility="private")
    tong_headers = await login_headers("tong", "demo12345")

    resp = await client.get(f"/api/v1/contacts/{private.id}/timeline", headers=tong_headers)
    assert resp.status_code == 404
