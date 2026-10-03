"""contacts 模块数据访问层：只拼查询条件与取数，不含业务规则。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.contacts.models import Contact, ImportantDate
from app.modules.records.models import Activity, ActivityParticipant
from app.services.permission import readable_condition

# 列表查询的统一取数形状：(Contact, 所有者展示名)
_ContactRow = Row

# "最近联系"过滤的取值（dashboard 统计与名册过滤共用此字典，口径单一）
ACTIVITY_FILTER_VALUES = ("recent_30d", "stale_180d")


def _last_activity_subquery() -> Select:
    """"联系人最近一次参与活动"的关联子查询（口径唯一实现点，单点维护）。"""
    return (
        select(func.max(Activity.occurred_at))
        .join(ActivityParticipant, ActivityParticipant.activity_id == Activity.id)
        .where(ActivityParticipant.contact_id == Contact.id, Activity.is_active.is_(True))
        .correlate(Contact)
        .scalar_subquery()
    )


async def find_readable_contacts(
    db: AsyncSession,
    user,
    *,
    tier: str | None = None,
    search: str | None = None,
    activity: str | None = None,
    include_archived: bool = False,
) -> list[_ContactRow]:
    """按读取范围查联系人列表，附带所有者展示名。

    search 同时模糊匹配 姓名/昵称；activity 按"最近联系"口径过滤
    （recent_30d=近 30 天有活动；stale_180d=超过 180 天无活动或从未记录，仅 direct）。
    """
    stmt = (
        select(Contact, User.display_name.label("owner_display_name"))
        .join(User, User.id == Contact.owner_user_id)
        .where(readable_condition(Contact, user))
    )
    if not include_archived:
        stmt = stmt.where(Contact.status == "active")
    if tier is not None:
        stmt = stmt.where(Contact.tier == tier)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            Contact.name.ilike(pattern) | Contact.nickname.ilike(pattern)
        )
    if activity is not None:
        stmt = stmt.where(_activity_filter_condition(activity))
    stmt = stmt.order_by(Contact.updated_at.desc())
    return list((await db.execute(stmt)).all())


def _activity_filter_condition(activity: str):
    """构造"最近联系"过滤条件（与 activity_stats 统计共用同一子查询口径）。"""
    last_at = _last_activity_subquery()
    if activity == "recent_30d":
        return last_at >= _recent_threshold()
    # stale_180d：直接联系人且（超 180 天无活动 或 从无活动记录）
    return (Contact.tier == "direct") & (
        (last_at < _stale_threshold()) | last_at.is_(None)
    )


def _recent_threshold() -> datetime:
    """近 30 天的起点时刻。"""
    return datetime.now(UTC) - timedelta(days=30)


def _stale_threshold() -> datetime:
    """半年（180 天）的起点时刻。"""
    return datetime.now(UTC) - timedelta(days=180)


async def find_activity_report(db: AsyncSession, user) -> dict:
    """联系活动报告（统计 + 名单，口径与列表过滤一致）。

    返回 total_contacts / recent_contacted / stale_half_year 三个数字，
    以及 stale_names（半年未联系：姓名 + 最近活动说明）与 recent_names（近 30 天联系）。
    统计与名单同源一次计算，避免数字与名单脱节（AI 工具因此一步可答）。
    """
    last_at = _last_activity_subquery()
    stmt = select(Contact, last_at.label("last_at")).where(
        readable_condition(Contact, user), Contact.status == "active"
    )
    rows = list((await db.execute(stmt)).all())

    stale_entries: list[tuple[str, str]] = []
    recent_names: list[str] = []
    for contact, last in rows:
        if last is not None and last >= _recent_threshold():
            recent_names.append(contact.display_name)
        if contact.tier == "direct" and (last is None or last < _stale_threshold()):
            note = "从无活动记录" if last is None else f"最近一次 {last.date().isoformat()}"
            stale_entries.append((contact.display_name, note))

    return {
        "total_contacts": len(rows),
        "recent_contacted": len(recent_names),
        "stale_half_year": len(stale_entries),
        "stale_names": stale_entries,
        "recent_names": recent_names,
    }


async def find_activity_stats(db: AsyncSession, user) -> dict[str, int]:
    """联系统计（主页卡片）：总数 / 近 30 天联系 / 半年未联系（口径与列表过滤一致）。"""
    report = await find_activity_report(db, user)
    return {
        "total_contacts": report["total_contacts"],
        "recent_contacted": report["recent_contacted"],
        "stale_half_year": report["stale_half_year"],
    }


async def get_readable_contact(db: AsyncSession, user, contact_id: int) -> Contact | None:
    """按 id 取当前用户可读的联系人；不可见一律返回 None（上层转 404）。"""
    stmt = select(Contact).where(Contact.id == contact_id, readable_condition(Contact, user))
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_readable_dates(db: AsyncSession, user, contact_id: int) -> list[ImportantDate]:
    """取某联系人下当前用户可读的重要日期（按 D7 对日期自身的可见性过滤）。"""
    stmt = (
        select(ImportantDate)
        .where(ImportantDate.contact_id == contact_id, readable_condition(ImportantDate, user))
        .order_by(ImportantDate.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_all_readable_dates(db: AsyncSession, user) -> list[tuple[ImportantDate, Contact]]:
    """取当前用户可读的全部重要日期，附带所属联系人（提醒引擎/聚合的全量源）。

    只取在册联系人（archived 联系人的日期不再提醒）。
    """
    stmt = (
        select(ImportantDate, Contact)
        .join(Contact, Contact.id == ImportantDate.contact_id)
        .where(readable_condition(ImportantDate, user), Contact.status == "active")
        .order_by(ImportantDate.id)
    )
    return list((await db.execute(stmt)).all())


async def find_readable_contacts_by_ids(
    db: AsyncSession, user, contact_ids: list[int]
) -> dict[int, Contact]:
    """按 id 批量取可读联系人映射（不可读的 id 不出现在结果中，D7）。"""
    if not contact_ids:
        return {}
    stmt = select(Contact).where(Contact.id.in_(contact_ids), readable_condition(Contact, user))
    contacts = (await db.execute(stmt)).scalars().all()
    return {contact.id: contact for contact in contacts}


async def find_family_duplicates(
    db: AsyncSession,
    user,
    *,
    name: str,
    nickname: str | None,
    exclude_contact_id: int | None = None,
) -> list[tuple[Contact, str]]:
    """家庭范围内同名检测（D7 细化）：命中姓名全等或昵称全等的在册联系人。

    返回 (联系人, 所有者展示名) 行，供 service 直接组装提醒。
    姓名为空时跳过姓名条件——否则会命中所有姓名同样为空的 edge 联系人（只填了昵称的那些）。
    """
    cleaned_name = name.strip()
    cleaned_nickname = (nickname or "").strip()

    match_conditions = []
    if cleaned_name:
        match_conditions.append(Contact.name == cleaned_name)
    if cleaned_nickname:
        match_conditions.append(Contact.nickname == cleaned_nickname)
    if not match_conditions:
        return []

    stmt = (
        select(Contact, User.display_name.label("owner_display_name"))
        .join(User, User.id == Contact.owner_user_id)
        .where(
            readable_condition(Contact, user),
            Contact.status == "active",
            *match_conditions,
        )
        .limit(5)
    )
    if exclude_contact_id is not None:
        stmt = stmt.where(Contact.id != exclude_contact_id)
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def find_geo_located_contacts(db: AsyncSession, user) -> list[Contact]:
    """取当前用户可读、在册且有坐标缓存的有效联系人（地图页数据源，D7 过滤）。"""
    stmt = select(Contact).where(
        readable_condition(Contact, user),
        Contact.status == "active",
        Contact.location_lat.is_not(None),
        Contact.location_lng.is_not(None),
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_distinct_schools(db: AsyncSession, user) -> list[str]:
    """当前用户可读范围内的毕业院校去重列表（校友查找/表单选择数据源）。"""
    stmt = (
        select(Contact.school_name)
        .where(
            readable_condition(Contact, user),
            Contact.status == "active",
            Contact.school_name.is_not(None),
        )
        .distinct()
        .order_by(Contact.school_name)
    )
    return [name for (name,) in (await db.execute(stmt)).all() if name]
