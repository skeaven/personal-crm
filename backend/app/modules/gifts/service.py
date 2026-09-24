"""gifts 模块服务层：礼物往来与愿望清单的业务规则（含愿望转礼物状态机）。"""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.contacts.repository import get_readable_contact
from app.modules.gifts import repository as gifts_repo
from app.modules.gifts.models import Gift, WishlistItem
from app.modules.gifts.schemas import (
    GiftCreate,
    GiftOut,
    GiftUpdate,
    WishlistConvertOut,
    WishlistCreate,
    WishlistOut,
    WishlistUpdate,
)
from app.services.permission import ensure_can_write


async def _ensure_contact_readable(db: AsyncSession, user: User, contact_id: int | None) -> None:
    """关联联系人必须对当前用户可读（家庭共享与私密的边界统一校验）。"""
    if contact_id is None:
        return
    contact = await get_readable_contact(db, user, contact_id)
    if contact is None:
        raise ValidationError("关联的联系人不可见")


def _to_gift_out(gift: Gift, owner_display_name: str) -> GiftOut:
    """组装礼物输出契约。"""
    gift.owner_display_name = owner_display_name
    return GiftOut.model_validate(gift)


def _to_wishlist_out(item: WishlistItem, owner_display_name: str) -> WishlistOut:
    """组装愿望输出契约。"""
    item.owner_display_name = owner_display_name
    return WishlistOut.model_validate(item)


async def create_gift(db: AsyncSession, user: User, data: GiftCreate) -> GiftOut:
    """创建礼物往来记录；金额字符串转 Decimal 落库。"""
    await _ensure_contact_readable(db, user, data.contact_id)
    fields = data.model_dump()
    if data.amount is not None:
        fields["amount"] = Decimal(data.amount)
    gift = Gift(**fields, owner_user_id=user.id, family_id=user.family_id)
    db.add(gift)
    await db.flush()
    return _to_gift_out(gift, user.display_name)


async def list_gifts(
    db: AsyncSession,
    user: User,
    *,
    search: str | None,
    direction: str | None,
    contact_id: int | None,
) -> list[GiftOut]:
    """列出可读礼物（送出/收到日期新→旧）。"""
    rows = await gifts_repo.find_readable_gifts(
        db, user, search=search, direction=direction, contact_id=contact_id
    )
    return [_to_gift_out(gift, owner_name) for gift, owner_name in rows]


async def get_gift(db: AsyncSession, user: User, gift_id: int) -> GiftOut:
    """读取礼物详情；不可见按 404 处理。"""
    gift = await gifts_repo.get_readable_gift(db, user, gift_id)
    if gift is None:
        raise NotFoundError("礼物记录不存在")
    owner = await db.get(User, gift.owner_user_id)
    return _to_gift_out(gift, owner.display_name if owner else "未知")


async def update_gift(db: AsyncSession, user: User, gift_id: int, data: GiftUpdate) -> GiftOut:
    """更新礼物（仅所有者）。"""
    gift = await gifts_repo.get_readable_gift(db, user, gift_id)
    if gift is None:
        raise NotFoundError("礼物记录不存在")
    ensure_can_write(user, gift)

    updates = data.model_dump(exclude_unset=True)
    if "contact_id" in updates:
        await _ensure_contact_readable(db, user, updates["contact_id"])
    if "amount" in updates and updates["amount"] is not None:
        updates["amount"] = Decimal(updates["amount"])
    for field, value in updates.items():
        setattr(gift, field, value)
    await db.flush()
    await db.refresh(gift)
    return _to_gift_out(gift, user.display_name)


async def delete_gift(db: AsyncSession, user: User, gift_id: int) -> None:
    """删除礼物记录（仅所有者）。被愿望回链的记录删除时清空回链，避免悬挂引用。"""
    gift = await gifts_repo.get_readable_gift(db, user, gift_id)
    if gift is None:
        raise NotFoundError("礼物记录不存在")
    ensure_can_write(user, gift)

    from sqlalchemy import update

    from app.modules.gifts.models import WishlistItem

    await db.execute(
        update(WishlistItem)
        .where(WishlistItem.converted_gift_id == gift_id)
        .values(converted_gift_id=None)
    )
    await db.delete(gift)
    await db.flush()


async def create_wishlist_item(
    db: AsyncSession, user: User, data: WishlistCreate
) -> WishlistOut:
    """创建愿望清单项。"""
    await _ensure_contact_readable(db, user, data.contact_id)
    fields = data.model_dump()
    if data.amount is not None:
        fields["amount"] = Decimal(data.amount)
    item = WishlistItem(**fields, owner_user_id=user.id, family_id=user.family_id)
    db.add(item)
    await db.flush()
    return _to_wishlist_out(item, user.display_name)


async def list_wishlist(
    db: AsyncSession, user: User, *, search: str | None, status: str | None, contact_id: int | None
) -> list[WishlistOut]:
    """列出可读愿望（目标日期近→远，无日期的排后）。"""
    rows = await gifts_repo.find_readable_wishlist(
        db, user, search=search, status=status, contact_id=contact_id
    )
    return [_to_wishlist_out(item, owner_name) for item, owner_name in rows]


async def list_contact_gifts(
    db: AsyncSession, user: User, *, contact_id: int
) -> list[GiftOut]:
    """联系人礼物时间线源（全量、日期降序；归并由聚合层完成）。"""
    rows = await gifts_repo.find_contact_gifts(db, user, contact_id=contact_id)
    owner = await db.get(User, rows[0].owner_user_id) if rows else None
    return [_to_gift_out(gift, owner.display_name if owner else "未知") for gift in rows]


async def list_upcoming_wishes(
    db: AsyncSession, user: User, *, statuses: tuple[str, ...], with_target_date: bool = False
) -> list[WishlistOut]:
    """按状态集合列出愿望（待办聚合用：定了送出日的 想送/已购买 项）。"""
    rows = await gifts_repo.find_readable_wishlist(
        db, user, statuses=statuses, with_target_date=with_target_date
    )
    return [_to_wishlist_out(item, owner_name) for item, owner_name in rows]


async def update_wishlist(
    db: AsyncSession, user: User, item_id: int, data: WishlistUpdate
) -> WishlistOut:
    """更新愿望（仅所有者）。"""
    item = await gifts_repo.get_readable_wishlist(db, user, item_id)
    if item is None:
        raise NotFoundError("愿望不存在")
    ensure_can_write(user, item)

    updates = data.model_dump(exclude_unset=True)
    if "contact_id" in updates:
        await _ensure_contact_readable(db, user, updates["contact_id"])
    if "amount" in updates and updates["amount"] is not None:
        updates["amount"] = Decimal(updates["amount"])
    for field, value in updates.items():
        setattr(item, field, value)
    await db.flush()
    await db.refresh(item)
    return _to_wishlist_out(item, user.display_name)


async def delete_wishlist(db: AsyncSession, user: User, item_id: int) -> None:
    """删除愿望（仅所有者）。"""
    item = await gifts_repo.get_readable_wishlist(db, user, item_id)
    if item is None:
        raise NotFoundError("愿望不存在")
    ensure_can_write(user, item)
    await db.delete(item)
    await db.flush()


async def convert_wishlist_to_gift(
    db: AsyncSession, user: User, item_id: int
) -> WishlistConvertOut:
    """愿望送出 → 生成礼物记录并闭环状态机（仅所有者）。

    幂等保护：已转换（status=given）的愿望重复转换报 400，防止重复人情账。
    """
    item = await gifts_repo.get_readable_wishlist(db, user, item_id)
    if item is None:
        raise NotFoundError("愿望不存在")
    ensure_can_write(user, item)
    if item.status == "given":
        raise BusinessError("该愿望已送出，不能重复转换")

    gift = Gift(
        contact_id=item.contact_id,
        direction="given",
        title=item.title,
        amount=item.amount,
        currency=item.currency,
        given_at=date.today(),
        link=item.link,
        description=item.description,
        owner_user_id=user.id,
        family_id=user.family_id,
    )
    db.add(gift)
    await db.flush()

    item.status = "given"
    item.converted_gift_id = gift.id
    await db.flush()
    await db.refresh(item)

    return WishlistConvertOut(
        gift=_to_gift_out(gift, user.display_name),
        item=_to_wishlist_out(item, user.display_name),
    )
