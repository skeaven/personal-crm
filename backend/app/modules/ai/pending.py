"""ai 模块写入确认队列：提议入队 → 用户确认 → 以提议人身份执行（D11 红线）。

执行器表 EXECUTORS 是"工具名 → 真实落库函数"的唯一映射；
确认者可以是提议人的家庭成员（家庭共同决定），执行身份恒为提议人，权限与手写一致。
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError, NotFoundError
from app.modules.ai.models import PendingAction
from app.modules.ai.registry import parse_iso_date, resolve_contact_name
from app.modules.auth.models import User
from app.modules.records import service as records_service
from app.modules.records.schemas import ActivityCreate, TaskCreate


async def propose(
    db: AsyncSession, user: User, tool_name: str, payload: dict, reason: str | None = None
) -> PendingAction:
    """写入提议入队（status=pending，不触达业务表）。"""
    action = PendingAction(
        family_id=user.family_id,
        requested_by_user_id=user.id,
        tool_name=tool_name,
        payload=payload,
        reason=reason,
        status="pending",
    )
    db.add(action)
    await db.flush()
    return action


async def list_pending(db: AsyncSession, user: User) -> list[PendingAction]:
    """当前用户的待确认提议（自己发起的；家庭内其他人的提议各自可见自己的）。"""
    stmt = (
        select(PendingAction)
        .where(PendingAction.requested_by_user_id == user.id, PendingAction.status == "pending")
        .order_by(PendingAction.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def _resolve_contact_id(
    db: AsyncSession, user: User, payload: dict
) -> int | None:
    """payload.contact_name → 联系人 id；未提供或找不到返回 None/报错由调用方定。"""
    name = payload.get("contact_name")
    if not name:
        return None
    resolved = await resolve_contact_name(db, user, name)
    if resolved is None:
        raise BusinessError(f"没有找到联系人「{name}」，请先在名册中记录")
    return resolved


async def _exec_create_task(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行建待办：contact_name 解析、日期解析后走 records service 正常创建。"""
    contact_id = await _resolve_contact_id(db, user, payload)
    due_at = (
        datetime.combine(
            parse_iso_date(str(payload["due_at"]), "due_at"), datetime.min.time(), tzinfo=UTC
        )
        if payload.get("due_at")
        else None
    )
    task = await records_service.create_task(
        db, user, TaskCreate(
            title=str(payload["title"]),
            contact_id=contact_id,
            due_at=due_at,
        )
    )
    return {"ok": True, "message": f"待办已创建（id={task.id}）：{task.title}"}


async def _exec_create_activity(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行记活动：参与者名逐个解析（不可读/不存在即失败并说明）。"""
    occurred = parse_iso_date(str(payload["occurred_at"]), "occurred_at")
    occurred_dt = datetime.combine(occurred, datetime.min.time(), tzinfo=UTC)

    participant_ids: list[int] = []
    for name in payload.get("participant_names", []):
        resolved = await resolve_contact_name(db, user, name)
        if resolved is None:
            raise BusinessError(f"没有找到参与者「{name}」，请先在名册中记录")
        participant_ids.append(resolved)

    activity = await records_service.create_activity(
        db, user, ActivityCreate(
            title=str(payload["title"]),
            occurred_at=occurred_dt,
            location=payload.get("location"),
            participant_ids=participant_ids,
        )
    )
    return {"ok": True, "message": f"活动已记录（id={activity.id}）：{activity.title}"}


async def _exec_create_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行建联系人：走 contacts 正常创建（自带同名检测 D7）；被拦截就把提醒
    写进 result——绝不用 confirm_duplicate=True 绕过，同名合并是人该做的决定。"""
    from app.modules.contacts import service as contacts_service
    from app.modules.contacts.schemas import ContactCreate

    response = await contacts_service.create_contact(db, user, ContactCreate(**payload))
    if not response.created:
        names = "、".join(w.display_name for w in response.duplicate_warnings) or "同名联系人"
        return {
            "ok": False,
            "error": f"同名提醒：{names} 已存在，未创建。可拒绝此提议，或去名册处理",
        }
    assert response.contact is not None
    return {
        "ok": True,
        "message": f"联系人已创建（id={response.contact.id}）：{response.contact.display_name}",
    }


EXECUTORS = {
    "create_task": _exec_create_task,
    "create_activity": _exec_create_activity,
    "create_contact": _exec_create_contact,
}


async def approve(db: AsyncSession, user: User, action_id: int) -> PendingAction:
    """确认提议并执行：执行身份恒为提议人（D7），失败原因记入 result 不静默。"""
    action = await db.get(PendingAction, action_id)
    if action is None:
        raise NotFoundError("提议不存在")
    if action.status != "pending":
        raise BusinessError("该提议已处理过")

    requester = await db.get(User, action.requested_by_user_id)
    if requester is None:
        raise BusinessError("提议人不存在，无法执行")

    action.status = "approved"
    action.decided_by = user.id
    action.decided_at = datetime.now(UTC)

    executor = EXECUTORS.get(action.tool_name)
    if executor is None:
        action.status = "executed"
        action.result = {"ok": False, "error": f"未知工具 {action.tool_name}"}
        await db.flush()
        return action

    try:
        result = await executor(db, requester, action.payload)
        action.status = "executed"
        action.result = result
    except BusinessError as exc:
        action.status = "executed"
        action.result = {"ok": False, "error": exc.message}
    action.executed_at = datetime.now(UTC)
    await db.flush()
    return action


async def reject(db: AsyncSession, user: User, action_id: int) -> PendingAction:
    """拒绝提议（终态，不可逆）。"""
    action = await db.get(PendingAction, action_id)
    if action is None:
        raise NotFoundError("提议不存在")
    if action.status != "pending":
        raise BusinessError("该提议已处理过")
    action.status = "rejected"
    action.decided_by = user.id
    action.decided_at = datetime.now(UTC)
    await db.flush()
    return action


def to_dict(action: PendingAction) -> dict:
    """提议的 API 输出形状（payload 原样透传给确认 UI）。"""
    return {
        "id": action.id,
        "tool_name": action.tool_name,
        "payload": action.payload,
        "status": action.status,
        "result": action.result,
        "created_at": action.created_at.isoformat(),
    }
