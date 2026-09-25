"""funds 模块数据访问层：资金流水的查询拼装。"""


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.funds.models import FundFlow
from app.services.permission import readable_condition


async def find_readable_fund_flows(
    db: AsyncSession,
    user,
    *,
    search: str | None = None,
    direction: str | None = None,
    category: str | None = None,
    status: str | None = None,
    contact_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[FundFlow, str]]:
    """按读取范围查资金流水（发生日新→旧），支持搜索与多维过滤组合。

    search 模糊匹配说明文本；status=pending 时按应还日升序（快到期的在前）。
    """
    stmt = (
        select(FundFlow, User.display_name.label("owner_display_name"))
        .join(User, User.id == FundFlow.owner_user_id)
        .where(readable_condition(FundFlow, user))
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(FundFlow.description.ilike(pattern))
    if direction is not None:
        stmt = stmt.where(FundFlow.direction == direction)
    if category is not None:
        stmt = stmt.where(FundFlow.category == category)
    if contact_id is not None:
        stmt = stmt.where(FundFlow.contact_id == contact_id)
    if status is not None:
        stmt = stmt.where(FundFlow.status == status)

    if status == "pending":
        stmt = stmt.order_by(FundFlow.due_at.asc().nulls_last())
    else:
        stmt = stmt.order_by(FundFlow.occurred_at.desc(), FundFlow.id.desc())
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return list((await db.execute(stmt)).all())


async def count_readable_fund_flows(
    db: AsyncSession,
    user,
    *,
    search: str | None = None,
    direction: str | None = None,
    category: str | None = None,
    status: str | None = None,
    contact_id: int | None = None,
) -> int:
    """统计可读资金流水总数（过滤条件必须与 find_readable_fund_flows 保持一致）。"""
    stmt = (
        select(func.count()).select_from(FundFlow).where(readable_condition(FundFlow, user))
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(FundFlow.description.ilike(pattern))
    if direction is not None:
        stmt = stmt.where(FundFlow.direction == direction)
    if category is not None:
        stmt = stmt.where(FundFlow.category == category)
    if contact_id is not None:
        stmt = stmt.where(FundFlow.contact_id == contact_id)
    if status is not None:
        stmt = stmt.where(FundFlow.status == status)
    return (await db.execute(stmt)).scalar_one()


async def get_readable_fund_flow(db: AsyncSession, user, fund_id: int) -> FundFlow | None:
    """按 id 取当前用户可读的资金流水；不可见一律 None（上层转 404）。"""
    stmt = select(FundFlow).where(FundFlow.id == fund_id, readable_condition(FundFlow, user))
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_contact_fund_flows(
    db: AsyncSession, user, *, contact_id: int
) -> list[FundFlow]:
    """取联系人名下全部资金流水（发生日降序，时间线数据源）。"""
    stmt = (
        select(FundFlow)
        .where(FundFlow.contact_id == contact_id, readable_condition(FundFlow, user))
        .order_by(FundFlow.occurred_at.desc(), FundFlow.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())
