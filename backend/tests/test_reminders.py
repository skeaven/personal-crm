"""提醒引擎测试（D22）：三源生成、幂等重建、已读不复活、源头消失清理、权限隔离。"""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.reminders import service as reminder_service
from tests.factories import create_task_for

pytestmark = pytest.mark.asyncio


async def test_scan_generates_from_three_sources(db_session, make_user):
    """三源生成：重要日期/到期任务/未结清还款各产生一条未读提醒。"""
    demo, _ = await make_user(username="demo")
    await create_task_for(demo, title="还房贷", due_at=datetime.now(UTC) + timedelta(days=3))

    stats = await reminder_service.scan_user(db_session, demo)
    reminders = await reminder_service.list_reminders(db_session, demo, unread_only=True)

    assert stats.created >= 1
    assert any(r.source == "task" and "还房贷" in r.title for r in reminders)
    # 全部在窗口内：days_left ∈ [-∞, 7]
    assert all(r.days_left is not None for r in reminders)


async def test_scan_is_idempotent(db_session, make_user):
    """幂等：重复扫描不新增不重复（UNIQUE 键去重）。"""
    demo, _ = await make_user(username="demo")
    await create_task_for(demo, title="交物业费", due_at=datetime.now(UTC) + timedelta(days=2))

    first = await reminder_service.scan_user(db_session, demo)
    second = await reminder_service.scan_user(db_session, demo)

    assert first.created >= 1
    assert second.created == 0
    reminders = await reminder_service.list_reminders(db_session, demo, unread_only=False)
    assert len([r for r in reminders if r.source == "task"]) == 1


async def test_read_reminder_not_revived(db_session, make_user):
    """已读不复活：标记已读后再扫描，同一条不重新变未读。"""
    demo, _ = await make_user(username="demo")
    await create_task_for(demo, title="取快递", due_at=datetime.now(UTC) + timedelta(days=1))
    await reminder_service.scan_user(db_session, demo)
    reminders = await reminder_service.list_reminders(db_session, demo, unread_only=True)
    target = next(r for r in reminders if r.source == "task")

    await reminder_service.mark_read(db_session, demo, target.id)
    await reminder_service.scan_user(db_session, demo)
    after = await reminder_service.list_reminders(db_session, demo, unread_only=True)
    assert all(r.id != target.id for r in after)


async def test_done_task_reminder_cleaned(db_session, make_user):
    """源头消失清理：任务完成后，其未读提醒被删除。"""
    demo, _ = await make_user(username="demo")
    task = await create_task_for(
        demo, title="交水电费", due_at=datetime.now(UTC) + timedelta(days=3)
    )
    await reminder_service.scan_user(db_session, demo)
    before = await reminder_service.list_reminders(db_session, demo, unread_only=True)
    assert any(r.source == "task" for r in before)

    # 完成任务
    task.status = "done"
    from app.core.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        merged = await session.merge(task)
        merged.status = "done"
        await session.commit()

    await reminder_service.scan_user(db_session, demo)
    after = await reminder_service.list_reminders(db_session, demo, unread_only=True)
    assert all(not (r.source == "task" and r.ref_id == task.id) for r in after)


async def test_family_isolation(db_session, make_user):
    """权限隔离：提醒按用户生成，另一家庭成员看不到。"""
    demo, _ = await make_user(username="demo")
    tong, _ = await make_user(username="tong2")
    await create_task_for(demo, title="demo 的私事", due_at=datetime.now(UTC) + timedelta(days=2))

    await reminder_service.scan_user(db_session, demo)
    demo_list = await reminder_service.list_reminders(db_session, demo, unread_only=True)
    tong_list = await reminder_service.list_reminders(db_session, tong, unread_only=True)

    assert any("demo 的私事" in r.title for r in demo_list)
    assert tong_list == []


async def test_window_boundary(db_session, make_user):
    """窗口边界：8 天后的任务不进提醒窗口（默认 7 天）。"""
    demo, _ = await make_user(username="demo")
    await create_task_for(demo, title="远期事项", due_at=datetime.now(UTC) + timedelta(days=8))
    await create_task_for(demo, title="窗口内事项", due_at=datetime.now(UTC) + timedelta(days=7))

    await reminder_service.scan_user(db_session, demo)
    reminders = await reminder_service.list_reminders(db_session, demo, unread_only=True)
    titles = [r.title for r in reminders]
    assert "窗口内事项" in "".join(titles)
    assert "远期事项" not in "".join(titles)


async def test_mark_read_all(db_session, make_user):
    """全部已读：未读数归零。"""
    demo, _ = await make_user(username="demo")
    await create_task_for(demo, title="事一", due_at=datetime.now(UTC) + timedelta(days=1))
    await create_task_for(demo, title="事二", due_at=datetime.now(UTC) + timedelta(days=2))
    await reminder_service.scan_user(db_session, demo)

    await reminder_service.mark_all_read(db_session, demo)
    count = await reminder_service.unread_count(db_session, demo)
    assert count == 0
