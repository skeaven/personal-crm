"""gifts 模块数据访问层：礼物往来与愿望清单的查询拼装。"""


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.gifts.models import Gift, WishlistItem
from app.services.permission import readable_condition


async def find_readable_gifts(
    db: AsyncSession,
    user,
    *,
    search: str | None = None,
    direction: str | None = None,
    contact_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[Gift, str]]:
    """按读取范围查礼物列表（新→旧），可按关键字/方向/联系人组合过滤。

    search 模糊匹配礼物名称与场合。
    """
    stmt = (
        select(Gift, User.display_name.label("owner_display_name"))
        .join(User, User.id == Gift.owner_user_id)
        .where(readable_condition(Gift, user))
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Gift.title.ilike(pattern) | Gift.occasion.ilike(pattern))
    if direction is not None:
        stmt = stmt.where(Gift.direction == direction)
    if contact_id is not None:
        stmt = stmt.where(Gift.contact_id == contact_id)
    stmt = stmt.order_by(Gift.given_at.desc().nulls_last(), Gift.id.desc())
    if limit is not None:
        # offset 分页：个人量级够用；并发新增会让跨页重复或遗漏，届时换 keyset（D19）
        stmt = stmt.limit(limit).offset(offset)
    return list((await db.execute(stmt)).all())


async def count_readable_gifts(
    db: AsyncSession,
    user,
    *,
    search: str | None = None,
    direction: str | None = None,
    contact_id: int | None = None,
) -> int:
    """统计可读礼物总数（过滤条件必须与 find_readable_gifts 保持一致）。"""
    stmt = select(func.count()).select_from(Gift).where(readable_condition(Gift, user))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Gift.title.ilike(pattern) | Gift.occasion.ilike(pattern))
    if direction is not None:
        stmt = stmt.where(Gift.direction == direction)
    if contact_id is not None:
        stmt = stmt.where(Gift.contact_id == contact_id)
    return (await db.execute(stmt)).scalar_one()


async def get_readable_gift(db: AsyncSession, user, gift_id: int) -> Gift | None:
    """按 id 取当前用户可读的礼物；不可见一律 None（上层转 404）。"""
    stmt = select(Gift).where(Gift.id == gift_id, readable_condition(Gift, user))
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_contact_gifts(db: AsyncSession, user, *, contact_id: int) -> list[Gift]:
    """取联系人名下全部礼物记录（送出/收到日期降序，时间线数据源）。"""
    stmt = (
        select(Gift)
        .where(
            Gift.contact_id == contact_id,
            readable_condition(Gift, user),
            Gift.given_at.is_not(None),
        )
        .order_by(Gift.given_at.desc(), Gift.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def find_readable_wishlist(
    db: AsyncSession,
    user,
    *,
    search: str | None = None,
    status: str | None = None,
    statuses: tuple[str, ...] | None = None,
    with_target_date: bool = False,
    contact_id: int | None = None,
) -> list[tuple[WishlistItem, str]]:
    """按读取范围查愿望列表（新→旧），支持关键字/单状态/多状态/目标日期过滤。

    statuses 与 status 二选一使用；with_target_date 只取定了送出日的项（待办聚合）。
    """
    stmt = (
        select(WishlistItem, User.display_name.label("owner_display_name"))
        .join(User, User.id == WishlistItem.owner_user_id)
        .where(readable_condition(WishlistItem, user))
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(WishlistItem.title.ilike(pattern))
    if status is not None:
        stmt = stmt.where(WishlistItem.status == status)
    if statuses is not None:
        stmt = stmt.where(WishlistItem.status.in_(statuses))
    if with_target_date:
        stmt = stmt.where(WishlistItem.target_date.is_not(None))
    if contact_id is not None:
        stmt = stmt.where(WishlistItem.contact_id == contact_id)
    stmt = stmt.order_by(WishlistItem.target_date.desc().nulls_last(), WishlistItem.id.desc())
    return list((await db.execute(stmt)).all())


async def get_readable_wishlist(
    db: AsyncSession, user, item_id: int
) -> WishlistItem | None:
    """按 id 取当前用户可读的愿望项；不可见一律 None（上层转 404）。"""
    stmt = select(WishlistItem).where(
        WishlistItem.id == item_id, readable_condition(WishlistItem, user)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
