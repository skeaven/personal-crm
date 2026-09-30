"""写入确认队列测试：确认执行（以提议人身份）、失败落账、拒绝、状态机防重。"""

from datetime import date

import pytest

from app.modules.ai import pending as pending_service
from tests.factories import (
    create_contact_for,
    create_family_user,
)

pytestmark = pytest.mark.asyncio


async def test_approve_executes_create_task(db_session, make_user):
    """确认建待办提议：以提议人身份落库，联系人/日期正确解析，状态转 executed。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")

    action = await pending_service.propose(
        db_session, demo, "create_task",
        {"title": "给老爸打电话", "contact_name": "老爸", "due_at": "2026-09-25"},
    )
    approved = await pending_service.approve(db_session, demo, action.id)

    assert approved.status == "executed"
    assert approved.result["ok"] is True

    from sqlalchemy import select

    from app.modules.records.models import Task

    tasks = list((await db_session.execute(select(Task))).scalars())
    assert len(tasks) == 1
    assert tasks[0].title == "给老爸打电话"
    assert tasks[0].contact_id == father.id
    assert tasks[0].due_at is not None and tasks[0].due_at.date() == date(2026, 9, 25)
    assert tasks[0].owner_user_id == demo.id  # 以提议人身份写入（D7）


async def test_approve_with_unknown_contact_records_failure(db_session, make_user):
    """确认时联系人解析失败：不抛异常，结果记 ok=False 与原因。"""
    demo, _ = await make_user(username="demo")
    action = await pending_service.propose(
        db_session, demo, "create_task",
        {"title": "找不存在的人", "contact_name": "查无此人"},
    )
    approved = await pending_service.approve(db_session, demo, action.id)
    assert approved.status == "executed"
    assert approved.result["ok"] is False
    assert "查无此人" in approved.result["error"]

    from sqlalchemy import func, select

    from app.modules.records.models import Task

    count = (await db_session.execute(select(func.count()).select_from(Task))).scalar()
    assert count == 0


async def test_reject_and_double_process_guard(db_session, make_user):
    """拒绝后不可再确认；已执行的不可重复处理。"""
    demo, _ = await make_user(username="demo")
    action = await pending_service.propose(db_session, demo, "create_task", {"title": "x"})

    rejected = await pending_service.reject(db_session, demo, action.id)
    assert rejected.status == "rejected"

    from app.core.errors import BusinessError

    with pytest.raises(BusinessError):
        await pending_service.approve(db_session, demo, action.id)


async def test_family_member_can_approve(db_session, make_user):
    """家庭成员可确认他人的提议（执行身份仍是提议人）。"""
    demo, _ = await make_user(username="demo")
    tong, _ = await create_family_user(family_id=demo.family_id, username="tong")
    action = await pending_service.propose(db_session, demo, "create_task", {"title": "家庭待办"})

    approved = await pending_service.approve(db_session, tong, action.id)
    assert approved.status == "executed" and approved.result["ok"] is True
    assert approved.decided_by == tong.id

    from sqlalchemy import select

    from app.modules.records.models import Task

    task = (await db_session.execute(select(Task))).scalar_one()
    assert task.owner_user_id == demo.id


async def test_approve_executes_create_contact(db_session, make_user):
    """确认建联系人：走 contacts 正常创建路径，电话落库，归属为提议人（D7）。"""
    demo, _ = await make_user(username="demo")

    action = await pending_service.propose(
        db_session, demo, "create_contact",
        {"tier": "direct", "last_name": "王", "nickname": "王姨", "phone": "13800000000"},
    )
    approved = await pending_service.approve(db_session, demo, action.id)

    assert approved.status == "executed"
    assert approved.result["ok"] is True
    assert "王姨" in approved.result["message"]

    from sqlalchemy import select

    from app.modules.contacts.models import Contact

    contacts = list((await db_session.execute(select(Contact))).scalars())
    assert len(contacts) == 1
    assert contacts[0].phone == "13800000000"
    assert contacts[0].owner_user_id == demo.id


async def test_approve_create_contact_blocked_by_duplicate(db_session, make_user):
    """撞同名：不落库、result 记原因——确认执行不得绕过同名保护（D7）。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, last_name="王", first_name="", nickname="王姨")

    action = await pending_service.propose(
        db_session, demo, "create_contact",
        {"tier": "direct", "last_name": "王", "nickname": "王姨"},
    )
    approved = await pending_service.approve(db_session, demo, action.id)

    assert approved.status == "executed"
    assert approved.result["ok"] is False
    assert "同名" in approved.result["error"]

    from sqlalchemy import func, select

    from app.modules.contacts.models import Contact

    count = (await db_session.execute(select(func.count()).select_from(Contact))).scalar_one()
    assert count == 1  # 只有预置那一条，提议没有落库
