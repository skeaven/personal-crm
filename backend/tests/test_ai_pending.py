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
    father = await create_contact_for(demo, name="陈建国", nickname="老爸")

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
        {"tier": "direct", "name": "王", "nickname": "王姨", "phone": "13800000000"},
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
    await create_contact_for(demo, name="王", nickname="王姨")

    action = await pending_service.propose(
        db_session, demo, "create_contact",
        {"tier": "direct", "name": "王", "nickname": "王姨"},
    )
    approved = await pending_service.approve(db_session, demo, action.id)

    assert approved.status == "executed"
    assert approved.result["ok"] is False
    assert "同名" in approved.result["error"]

    from sqlalchemy import func, select

    from app.modules.contacts.models import Contact

    count = (await db_session.execute(select(func.count()).select_from(Contact))).scalar_one()
    assert count == 1  # 只有预置那一条，提议没有落库


async def test_approve_legacy_payload_with_nickname_does_not_silently_drop_name(
    db_session, make_user
):
    """D23 之前入队的旧 payload 带昵称时，确认不得静默建出「姓名为空」的联系人。

    payload 是持久化 JSON：升级时可能躺着带 last_name/first_name 的旧行。
    新契约忽略这两个键，若不拦截就会把「王」丢掉、只留昵称建一条联系人——
    姓名静默丢失比报错更糟。
    """
    from sqlalchemy import select

    from app.modules.contacts.models import Contact

    demo, _ = await make_user(username="demo")
    action = await pending_service.propose(
        db_session, demo, "create_contact",
        {"tier": "direct", "last_name": "王", "nickname": "王姨"},
    )

    approved = await pending_service.approve(db_session, demo, action.id)

    assert approved.status == "executed"
    assert approved.result["ok"] is False
    contacts = list((await db_session.execute(select(Contact))).scalars())
    assert contacts == [], "旧 payload 不得落库（否则姓名字段静默丢失）"


async def test_approve_payload_failing_schema_records_failure_instead_of_raising(
    db_session, make_user
):
    """payload 过不了当前 schema 时必须记失败，而不是把异常抛出去。

    修复前抛的是 pydantic 的 ValidationError（不是 BusinessError，approve 接不住），
    结果是 500 且状态永远停在 pending——这条提议用户再也处理不掉。
    两种形状都要覆盖：无姓名的旧 payload（无昵称）与缺字段的新形状。
    """
    demo, _ = await make_user(username="demo")

    for payload in (
        {"tier": "direct", "last_name": "张", "first_name": "伟"},
        {"tier": "direct"},
    ):
        action = await pending_service.propose(
            db_session, demo, "create_contact", dict(payload)
        )
        approved = await pending_service.approve(db_session, demo, action.id)
        assert approved.status == "executed", f"{payload} 未被执行"
        assert approved.result["ok"] is False, f"{payload} 应记失败"
        assert approved.result["error"], f"{payload} 应给出失败原因"


async def test_propose_stores_preview_snapshot(db_session, make_user):
    """preview 与 payload 分离：执行器只消费 payload，preview 仅供确认面板渲染差异。"""
    demo, _ = await make_user(username="demo")

    action = await pending_service.propose(
        db_session,
        demo,
        "update_contact",
        {"contact_id": 39, "phone": "139"},
        preview={"before": {"phone": "138"}},
    )

    assert action.preview == {"before": {"phone": "138"}}
    assert action.payload == {"contact_id": 39, "phone": "139"}


async def test_propose_without_preview_stores_null(db_session, make_user):
    """create 类不填 preview；列可空，面板按 payload 直读渲染。"""
    demo, _ = await make_user(username="demo")

    action = await pending_service.propose(db_session, demo, "create_task", {"title": "买花"})

    assert action.preview is None


async def test_approve_update_contact_changes_only_submitted_fields(db_session, make_user):
    """确认改联系人：只改提交字段，其余字段原样保留。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴", phone="138", organization="极星科技")
    action = await pending_service.propose(
        db_session, demo, "update_contact", {"contact_id": contact.id, "phone": "139"}
    )

    await pending_service.approve(db_session, demo, action.id)

    from app.modules.contacts import service as contacts_service

    detail = await contacts_service.get_contact(db_session, demo, contact.id)
    assert detail.phone == "139"
    assert detail.organization == "极星科技", "未提交的字段不该被清空"


async def test_approve_update_on_missing_contact_records_failure(db_session, make_user):
    """提议引用的联系人已不存在：记 ok=False 让人看见失败，不 500 卡在 pending。"""
    demo, _ = await make_user(username="demo")
    action = await pending_service.propose(
        db_session, demo, "update_contact", {"contact_id": 999999, "phone": "139"}
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.status == "executed"
    assert result.result["ok"] is False


async def test_approve_delete_contact_archives_it(db_session, make_user):
    """确认归档：联系人从名册消失（软删），但记录仍在、不是物理删除。

    软删口径由 HTTP 侧 test_contacts.py::test_archive_is_soft_delete 钉死：
    列表不可见、详情仍可读（status=archived）——归档工具走的是同一个 service 函数，
    行为必须与 UI 的删除按钮完全一致。
    """
    from sqlalchemy import select

    from app.modules.contacts import service as contacts_service
    from app.modules.contacts.models import Contact

    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")
    action = await pending_service.propose(
        db_session, demo, "delete_contact", {"contact_id": contact.id}
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.result["ok"] is True
    roster = await contacts_service.list_contacts(db_session, demo, tier=None, search=None)
    assert all(item.id != contact.id for item in roster), "归档后应从名册消失"
    row = (
        await db_session.execute(select(Contact).where(Contact.id == contact.id))
    ).scalar_one()
    assert row.status == "archived", "软删：行仍在，只是 status 变了"


async def test_approve_add_lunar_date_creates_it(db_session, make_user):
    """确认加农历生日：落库后能经 get_contact 读回，农历字段正确。"""
    from app.modules.contacts import service as contacts_service

    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")
    action = await pending_service.propose(
        db_session,
        demo,
        "add_important_date",
        {
            "contact_id": contact.id,
            "type": "birthday",
            "calendar": "lunar",
            "lunar_month": 9,
            "lunar_day": 24,
            "lunar_is_leap": False,
            "yearly": True,
            "reminder_lead_days": [7, 1],
        },
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.result["ok"] is True
    detail = await contacts_service.get_contact(db_session, demo, contact.id)
    assert [(d.lunar_month, d.lunar_day) for d in detail.dates] == [(9, 24)]


async def test_approve_delete_missing_date_records_failure(db_session, make_user):
    """提议引用的日期已被删：记 ok=False，不 500 卡在 pending。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴")
    action = await pending_service.propose(
        db_session,
        demo,
        "delete_important_date",
        {"contact_id": contact.id, "date_id": 999999},
    )

    result = await pending_service.approve(db_session, demo, action.id)

    assert result.status == "executed"
    assert result.result["ok"] is False
