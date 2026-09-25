"""funds 模块服务层：资金流水的业务规则（结清状态机）。"""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.contacts.repository import get_readable_contact
from app.modules.funds import repository as funds_repo
from app.modules.funds.models import FundFlow
from app.modules.funds.schemas import FundFlowCreate, FundFlowOut, FundFlowUpdate
from app.services.permission import ensure_can_write


async def _ensure_contact_readable(db: AsyncSession, user: User, contact_id: int | None) -> None:
    """关联联系人必须对当前用户可读（同 gifts 模块的边界校验）。"""
    if contact_id is None:
        return
    contact = await get_readable_contact(db, user, contact_id)
    if contact is None:
        raise ValidationError("关联的联系人不可见")


def _to_out(flow: FundFlow, owner_display_name: str) -> FundFlowOut:
    """组装资金流水输出契约。"""
    flow.owner_display_name = owner_display_name
    return FundFlowOut.model_validate(flow)


async def create_fund_flow(db: AsyncSession, user: User, data: FundFlowCreate) -> FundFlowOut:
    """创建资金流水：带应还日视为需结清（初始 pending），否则不涉及结清（NULL）。"""
    await _ensure_contact_readable(db, user, data.contact_id)
    fields = data.model_dump()
    fields["amount"] = Decimal(data.amount)
    flow = FundFlow(
        **fields,
        status="pending" if data.due_at is not None else None,
        owner_user_id=user.id,
        family_id=user.family_id,
    )
    db.add(flow)
    await db.flush()
    return _to_out(flow, user.display_name)


async def list_fund_flows(
    db: AsyncSession,
    user: User,
    *,
    search: str | None,
    direction: str | None,
    category: str | None,
    status: str | None,
    contact_id: int | None,
    limit: int | None = None,
    offset: int = 0,
) -> list[FundFlowOut]:
    """列出可读资金流水；pending 视图按应还日升序（主页还款提醒同口径）。"""
    rows = await funds_repo.find_readable_fund_flows(
        db,
        user,
        search=search,
        direction=direction,
        category=category,
        status=status,
        contact_id=contact_id,
        limit=limit,
        offset=offset,
    )
    return [_to_out(flow, owner_name) for flow, owner_name in rows]


async def count_fund_flows(
    db: AsyncSession,
    user: User,
    *,
    search: str | None,
    direction: str | None,
    category: str | None,
    status: str | None,
    contact_id: int | None,
) -> int:
    """可读资金流水总数（分页响应头 X-Total-Count 用）。"""
    return await funds_repo.count_readable_fund_flows(
        db,
        user,
        search=search,
        direction=direction,
        category=category,
        status=status,
        contact_id=contact_id,
    )


async def list_contact_fund_flows(
    db: AsyncSession, user: User, *, contact_id: int
) -> list[FundFlowOut]:
    """联系人资金时间线源（全量、发生日降序；归并由聚合层完成）。"""
    rows = await funds_repo.find_contact_fund_flows(db, user, contact_id=contact_id)
    owner = await db.get(User, rows[0].owner_user_id) if rows else None
    return [_to_out(flow, owner.display_name if owner else "未知") for flow in rows]


async def get_fund_flow(db: AsyncSession, user: User, fund_id: int) -> FundFlowOut:
    """读取资金流水详情；不可见按 404 处理。"""
    flow = await funds_repo.get_readable_fund_flow(db, user, fund_id)
    if flow is None:
        raise NotFoundError("资金记录不存在")
    owner = await db.get(User, flow.owner_user_id)
    return _to_out(flow, owner.display_name if owner else "未知")


async def update_fund_flow(
    db: AsyncSession, user: User, fund_id: int, data: FundFlowUpdate
) -> FundFlowOut:
    """更新资金流水（仅所有者）；status 变更维护 settled_at（结清盖日、重开清空）。

    due_at 补填时若流水原不涉及结清（status 为 NULL），自动进入 pending。
    """
    flow = await funds_repo.get_readable_fund_flow(db, user, fund_id)
    if flow is None:
        raise NotFoundError("资金记录不存在")
    ensure_can_write(user, flow)

    updates = data.model_dump(exclude_unset=True)
    if "contact_id" in updates:
        await _ensure_contact_readable(db, user, updates["contact_id"])
    if "amount" in updates and updates["amount"] is not None:
        updates["amount"] = Decimal(updates["amount"])

    for field, value in updates.items():
        setattr(flow, field, value)

    if updates.get("status") == "settled":
        if flow.settled_at is None:
            flow.settled_at = date.today()
    elif "status" in updates and updates["status"] != "settled":
        flow.settled_at = None
    if "due_at" in updates and flow.status is None and updates["due_at"] is not None:
        flow.status = "pending"

    await db.flush()
    await db.refresh(flow)
    return _to_out(flow, user.display_name)


async def delete_fund_flow(db: AsyncSession, user: User, fund_id: int) -> None:
    """删除资金流水（仅所有者）。"""
    flow = await funds_repo.get_readable_fund_flow(db, user, fund_id)
    if flow is None:
        raise NotFoundError("资金记录不存在")
    ensure_can_write(user, flow)
    await db.delete(flow)
    await db.flush()
