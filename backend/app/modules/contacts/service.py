"""contacts 模块服务层：业务规则（展示名、同名防线、升级、归档、日期、提醒）。"""

from collections import Counter
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.contacts import repository as contact_repo
from app.modules.contacts.models import TIER_DIRECT, Contact, ImportantDate
from app.modules.contacts.schemas import (
    ContactCreate,
    ContactCreateResponse,
    ContactDetailOut,
    ContactOut,
    ContactUpdate,
    DateReminder,
    DuplicateWarning,
    ImportantDateCreate,
    ImportantDateOut,
    ImportantDateUpdate,
    MapPointOut,
    MapPointsOut,
    ProvinceCountOut,
)
from app.modules.geo.geocoder import resolve_location
from app.modules.settings.service import KEY_GEO_AMAP, get_setting_value
from app.services.permission import ensure_can_write


async def _load_amap_key(db: AsyncSession) -> str | None:
    """读高德 Web 服务 key（settings 横切读，ARCHITECTURE 第 2 节）；未配置返回 None。"""
    config = await get_setting_value(db, KEY_GEO_AMAP)
    if not config:
        return None
    api_key = str(config.get("api_key") or "").strip()
    return api_key or None


async def _set_contact_location(
    db: AsyncSession, contact: Contact, location_text: str | None
) -> None:
    """解析位置文本并写坐标缓存列（D14），无条件覆盖，由调用方决定何时重算。

    语义：location 为空 → 三个缓存列一并清空；解析未命中 → source="none"
    （前端可提示"坐标未解析"），坐标置空；命中 → source=amap/static。
    """
    text = (location_text or "").strip()
    contact.location = text or None
    if not text:
        contact.location_lng = None
        contact.location_lat = None
        contact.location_source = None
        contact.location_province = None
        return
    result = await resolve_location(text, amap_key=await _load_amap_key(db))
    if result is None:
        contact.location_lng = None
        contact.location_lat = None
        contact.location_source = "none"
        contact.location_province = None
        return
    contact.location_lng = result.lng
    contact.location_lat = result.lat
    contact.location_source = result.source
    contact.location_province = result.province


def _to_out(contact: Contact, owner_display_name: str) -> ContactOut:
    """把 ORM 对象转换为输出契约。

    display_name 由模型层属性提供；owner_display_name 以瞬态属性注入供序列化读取。
    """
    contact.owner_display_name = owner_display_name
    return ContactOut.model_validate(contact)


def _build_warning(contact: Contact, owner_display_name: str) -> DuplicateWarning:
    """把命中的同名联系人转成前端可展示的提醒项。"""
    return DuplicateWarning(
        contact_id=contact.id,
        display_name=contact.display_name,
        owner_display_name=owner_display_name,
        tier=contact.tier,
    )


async def check_duplicates(
    db: AsyncSession, user: User, name: str, nickname: str | None
) -> list[DuplicateWarning]:
    """同名检测（D7 细化）：家庭范围内命中即返回提醒列表。"""
    hits = await contact_repo.find_family_duplicates(db, user, name=name, nickname=nickname)
    return [_build_warning(contact, owner_name) for contact, owner_name in hits]


async def create_contact(
    db: AsyncSession, user: User, data: ContactCreate
) -> ContactCreateResponse:
    """创建联系人：未确认前若命中同名则返回提醒，不落库（D7 细化决策）。"""
    warnings = await check_duplicates(db, user, data.name, data.nickname)
    if warnings and not data.confirm_duplicate:
        return ContactCreateResponse(created=False, duplicate_warnings=warnings)

    contact = Contact(
        **data.model_dump(exclude={"confirm_duplicate", "location"}),
        owner_user_id=user.id,
        family_id=user.family_id,
    )
    await _set_contact_location(db, contact, data.location)
    db.add(contact)
    await db.flush()
    return ContactCreateResponse(
        created=True,
        contact=_to_out(contact, user.display_name),
        duplicate_warnings=warnings,
    )


async def list_contacts(
    db: AsyncSession,
    user: User,
    *,
    tier: str | None,
    search: str | None,
    activity: str | None = None,
) -> list[ContactOut]:
    """列出可读联系人并转换为输出契约（activity 为主页统计卡跳转的同口径过滤）。"""
    rows = await contact_repo.find_readable_contacts(
        db, user, tier=tier, search=search, activity=activity
    )
    return [_to_out(contact, owner_name) for contact, owner_name in rows]


async def activity_stats(db: AsyncSession, user: User) -> dict[str, int]:
    """联系统计（主页卡片）：总数 / 近 30 天联系 / 半年未联系（口径单点在 repository）。"""
    return await contact_repo.find_activity_stats(db, user)


async def activity_report(db: AsyncSession, user: User) -> dict:
    """统计 + 名单（AI 工具用：一步给出"半年未联系是谁"，数字与名单同源不脱节）。"""
    return await contact_repo.find_activity_report(db, user)


async def map_points(db: AsyncSession, user: User) -> MapPointsOut:
    """地图页数据（D14）：可读联系人的坐标点 + 省份计数（choropleth 着色维度）。"""
    located = await contact_repo.find_geo_located_contacts(db, user)
    points = [
        MapPointOut(
            contact_id=contact.id,
            display_name=contact.display_name,
            tier=contact.tier,
            lng=contact.location_lng,
            lat=contact.location_lat,
        )
        for contact in located
    ]
    counter = Counter(
        contact.location_province or "未知" for contact in located
    )
    provinces = [
        ProvinceCountOut(name=name, count=count)
        for name, count in counter.most_common()
    ]
    return MapPointsOut(points=points, provinces=provinces)


async def _to_detail(db: AsyncSession, user: User, contact: Contact) -> ContactDetailOut:
    """组装详情输出：联系人全量 + 关联区块（详情页操作的统一返回形态）。"""
    owner = await db.get(User, contact.owner_user_id)
    owner_name = owner.display_name if owner else "未知"
    detail = ContactDetailOut.model_validate(_to_out(contact, owner_name))
    detail.dates = [
        ImportantDateOut.model_validate(d)
        for d in await contact_repo.list_readable_dates(db, user, contact.id)
    ]
    return detail


async def get_contact(db: AsyncSession, user: User, contact_id: int) -> ContactDetailOut:
    """读取联系人详情；不可见按 404 处理（不泄露私有数据存在性）。

    详情 = 联系人全量 + 关联区块（当前：重要日期；时间线/礼物/资金等后续增量挂载）。
    """
    contact = await contact_repo.get_readable_contact(db, user, contact_id)
    if contact is None:
        raise NotFoundError("联系人不存在")
    return await _to_detail(db, user, contact)


async def update_contact(
    db: AsyncSession, user: User, contact_id: int, data: ContactUpdate
) -> ContactDetailOut:
    """更新联系人（仅所有者）；tier 字段走专门的升级接口，此处忽略。"""
    contact = await contact_repo.get_readable_contact(db, user, contact_id)
    if contact is None:
        raise NotFoundError("联系人不存在")
    ensure_can_write(user, contact)

    updates = data.model_dump(exclude_unset=True, exclude={"tier"})
    if "location" in updates:
        # 位置变更才重算坐标缓存（D14）：值未变或只发其他字段时不触发外部解析
        new_location = updates.pop("location")
        if (new_location or None) != (contact.location or None):
            await _set_contact_location(db, contact, new_location)
    for field, value in updates.items():
        setattr(contact, field, value)
    await db.flush()
    await db.refresh(contact)  # reload 服务端生成的 updated_at，避免序列化期懒加载

    return await _to_detail(db, user, contact)


async def promote_contact(db: AsyncSession, user: User, contact_id: int) -> ContactDetailOut:
    """边缘联系人一键升级为直接联系人：只改 tier，数据无损（R6）。"""
    contact = await contact_repo.get_readable_contact(db, user, contact_id)
    if contact is None:
        raise NotFoundError("联系人不存在")
    ensure_can_write(user, contact)

    contact.tier = TIER_DIRECT
    await db.flush()
    await db.refresh(contact)  # 同上：reload onupdate 列

    return await _to_detail(db, user, contact)


async def archive_contact(db: AsyncSession, user: User, contact_id: int) -> None:
    """删除=归档（软删），保护历史关系边与生活流引用。"""
    contact = await contact_repo.get_readable_contact(db, user, contact_id)
    if contact is None:
        raise NotFoundError("联系人不存在")
    ensure_can_write(user, contact)

    contact.status = "archived"
    await db.flush()


async def get_display_name_map(
    db: AsyncSession, user: User, contact_ids: list[int]
) -> dict[int, str]:
    """批量取联系人展示名（不可读的 id 不在结果中）；聚合视图的联系人取名口径。"""
    contacts = await contact_repo.find_readable_contacts_by_ids(db, user, contact_ids)
    return {contact_id: contact.display_name for contact_id, contact in contacts.items()}


async def _ensure_date_writable(db: AsyncSession, user: User, contact_id: int) -> Contact:
    """日期写操作的前置校验：联系人可读且当前用户是其所有者（D7 与联系人编辑一致）。"""
    contact = await contact_repo.get_readable_contact(db, user, contact_id)
    if contact is None:
        raise NotFoundError("联系人不存在")
    ensure_can_write(user, contact)
    return contact


async def create_date(
    db: AsyncSession, user: User, contact_id: int, data: ImportantDateCreate
) -> ContactDetailOut:
    """为联系人创建重要日期；日期可见性强制跟随联系人（不产生独立泄露面）。"""
    contact = await _ensure_date_writable(db, user, contact_id)
    record = ImportantDate(
        **data.model_dump(),
        contact_id=contact_id,
        owner_user_id=user.id,
        family_id=user.family_id,
        visibility=contact.visibility,
    )
    db.add(record)
    await db.flush()
    return await _to_detail(db, user, contact)


async def update_date(
    db: AsyncSession, user: User, contact_id: int, date_id: int, data: ImportantDateUpdate
) -> ContactDetailOut:
    """更新重要日期（仅联系人所有者）；改历法时整体复核字段配套。"""
    contact = await _ensure_date_writable(db, user, contact_id)
    record = await db.get(ImportantDate, date_id)
    if record is None or record.contact_id != contact_id:
        raise NotFoundError("重要日期不存在")

    updates = data.model_dump(exclude_unset=True)
    merged = {
        "calendar": record.calendar,
        "date_solar": record.date_solar,
        "lunar_month": record.lunar_month,
        "lunar_day": record.lunar_day,
        **updates,
    }
    if merged["calendar"] == "solar" and merged["date_solar"] is None:
        raise ValidationError("公历日期必须提供 date_solar")
    if merged["calendar"] == "lunar" and (
        merged["lunar_month"] is None or merged["lunar_day"] is None
    ):
        raise ValidationError("农历日期必须提供 lunar_month 与 lunar_day")

    for field, value in updates.items():
        setattr(record, field, value)
    await db.flush()
    await db.refresh(contact)
    return await _to_detail(db, user, contact)


async def delete_date(
    db: AsyncSession, user: User, contact_id: int, date_id: int
) -> None:
    """删除重要日期（仅联系人所有者）。"""
    await _ensure_date_writable(db, user, contact_id)
    record = await db.get(ImportantDate, date_id)
    if record is None or record.contact_id != contact_id:
        raise NotFoundError("重要日期不存在")
    await db.delete(record)
    await db.flush()


async def upcoming_date_reminders(
    db: AsyncSession,
    user: User,
    *,
    today: date,
    default_lead_days: int = 7,
) -> list[DateReminder]:
    """计算当前用户可读的、已进入提醒窗口的重要日期（待办/主页共用的日期提醒口径）。

    窗口 = max(reminder_lead_days) 或默认 7 天；公历/农历的下一次发生日由历法引擎计算，
    生日过期为"滚动到明年"，永不进过期状态。
    """
    from app.modules.contacts.calendar import (
        lunar_display_name,
        next_lunar_occurrence,
        next_solar_occurrence,
    )

    reminders: list[DateReminder] = []
    for important_date, contact in await contact_repo.list_all_readable_dates(db, user):
        lead_days = important_date.reminder_lead_days or []
        window = max(lead_days) if lead_days else default_lead_days

        if important_date.calendar == "lunar":
            next_day = next_lunar_occurrence(
                important_date.lunar_month, important_date.lunar_day,
                important_date.lunar_is_leap, today,
            )
            label = lunar_display_name(
                important_date.lunar_month, important_date.lunar_day,
                important_date.lunar_is_leap,
            )
        else:
            next_day = next_solar_occurrence(important_date.date_solar, today)
            label = None

        days_left = (next_day - today).days
        if days_left > window:
            continue
        reminders.append(
            DateReminder(
                date_id=important_date.id,
                date_type=important_date.type,
                title=important_date.title,
                contact_id=contact.id,
                contact_name=contact.display_name,
                next_date=next_day,
                days_left=days_left,
                lunar_label=label,
            )
        )
    reminders.sort(key=lambda reminder: reminder.days_left)
    return reminders


async def list_schools(db: AsyncSession, user: User) -> list[str]:
    """毕业院校去重列表（家庭可读范围），供表单选择与校友筛选。"""
    return await contact_repo.list_distinct_schools(db, user)
