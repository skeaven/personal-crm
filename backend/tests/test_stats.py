"""主页统计测试：联系人总数 / 近 30 天联系 / 半年未联系（口径建在活动参与者表）。"""

from datetime import UTC, datetime, time, timedelta

import pytest

from tests.factories import (
    create_activity_for,
    create_contact_for,
    create_family_user,
    create_task_for,
)

pytestmark = pytest.mark.asyncio

_TODAY = datetime.combine(datetime.now(UTC).date(), time(12, 0), tzinfo=UTC)


def _days_ago(days: int) -> datetime:
    """相对今天的时刻（正午 UTC，转本地仍同一天）。"""
    return _TODAY - timedelta(days=days)


async def _stats(client, headers) -> dict:
    """调用统计接口并返回 JSON。"""
    resp = await client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_stats_counts_by_activity_recency(client, make_user, login_headers):
    """统计口径：总数含边缘；近期/久未只按 direct 联系人、以参与者表最近活动计。"""
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    father = await create_contact_for(demo, name="陈建国", nickname="老爸")
    mother = await create_contact_for(demo, name="陈秀兰", nickname="老妈")
    await create_contact_for(demo, name="张伟")
    await create_contact_for(demo, tier="edge", nickname="张小宝")

    # 老爸 3 天前参与活动（近期）；老妈 200 天前（半年未联系）；张伟从未记录（半年未联系）
    await create_activity_for(
        demo, title="家宴", occurred_at=_days_ago(3), participant_contact_ids=[father.id]
    )
    await create_activity_for(
        demo, title="久远的聚会", occurred_at=_days_ago(200), participant_contact_ids=[mother.id]
    )
    await create_task_for(demo, title="待办一")
    await create_task_for(demo, title="待办二")

    stats = await _stats(client, headers)
    assert stats["total_contacts"] == 4
    assert stats["recent_contacted"] == 1
    assert stats["stale_half_year"] == 2
    assert stats["open_tasks"] == 2


async def test_stats_visibility_scope(client, make_user, login_headers):
    """统计范围随可读性：家人看不到私密联系人，也不计入各卡片。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    await create_contact_for(demo, name="周明", visibility="private")
    father = await create_contact_for(demo, name="陈建国", visibility="family")
    await create_activity_for(
        demo, title="家宴", occurred_at=_days_ago(2), participant_contact_ids=[father.id]
    )
    tong_headers = await login_headers("tong", "demo12345")

    stats = await _stats(client, tong_headers)
    assert stats["total_contacts"] == 1
    assert stats["recent_contacted"] == 1
    assert stats["stale_half_year"] == 0


async def test_contacts_list_activity_filter(client, make_user, login_headers):
    """名册过滤 ?activity=recent_30d / stale_180d 与统计同口径（跳转联动）。"""
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    father = await create_contact_for(demo, name="陈建国")
    mother = await create_contact_for(demo, name="陈秀兰")
    await create_activity_for(
        demo, title="家宴", occurred_at=_days_ago(3), participant_contact_ids=[father.id]
    )
    await create_activity_for(
        demo, title="久远的聚会", occurred_at=_days_ago(200), participant_contact_ids=[mother.id]
    )

    recent = (
        await client.get("/api/v1/contacts?activity=recent_30d", headers=headers)
    ).json()
    assert [item["display_name"] for item in recent] == ["陈建国"]

    stale = (
        await client.get("/api/v1/contacts?activity=stale_180d", headers=headers)
    ).json()
    assert [item["display_name"] for item in stale] == ["陈秀兰"]
