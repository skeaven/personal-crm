"""ai 模块写入确认队列：提议入队 → 用户确认 → 以提议人身份执行（D11 红线）。

执行器表 EXECUTORS 是"工具名 → 真实落库函数"的唯一映射；
确认者可以是提议人的家庭成员（家庭共同决定），执行身份恒为提议人，权限与手写一致。
"""

from datetime import UTC, datetime

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError, NotFoundError
from app.modules.ai.executors import EXECUTORS  # noqa: F401  re-export：调用方与测试从本模块取
from app.modules.ai.models import PendingAction
from app.modules.auth.models import User


async def propose(
    db: AsyncSession,
    user: User,
    tool_name: str,
    payload: dict,
    reason: str | None = None,
    preview: dict | None = None,
) -> PendingAction:
    """写入提议入队（status=pending，不触达业务表）。

    preview 只服务确认面板的渲染（update 放改动字段的原值、delete 放实体摘要），
    执行器只读 payload——两者分离，避免渲染需求污染落库契约。
    """
    action = PendingAction(
        family_id=user.family_id,
        requested_by_user_id=user.id,
        tool_name=tool_name,
        payload=payload,
        preview=preview,
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
    except PydanticValidationError as exc:
        # pydantic 的 ValidationError 不是 BusinessError（app.core.errors 那个才是），
        # 不接住就会 500 且状态永远停在 pending——这条提议用户再也处理不掉。
        first = exc.errors()[0] if exc.errors() else {}
        action.status = "executed"
        action.result = {
            "ok": False,
            "error": f"提议内容与当前契约不符：{first.get('msg', '校验失败')}",
        }
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
    """提议的 API 输出形状（payload 与 preview 原样透传给确认 UI）。"""
    return {
        "id": action.id,
        "tool_name": action.tool_name,
        "payload": action.payload,
        "preview": action.preview,
        "status": action.status,
        "result": action.result,
        "created_at": action.created_at.isoformat(),
    }
