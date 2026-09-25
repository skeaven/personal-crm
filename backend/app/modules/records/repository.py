"""records 模块数据访问层：活动/任务的查询拼装（含跨模块只读 JOIN contacts/users）。"""

from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.contacts.models import Contact
from app.modules.records.models import Activity, ActivityImage, ActivityParticipant, Task
from app.services.permission import readable_condition


async def find_readable_activities(
    db: AsyncSession,
    user,
    *,
    search: str | None = None,
    from_time: datetime | None = None,
    contact_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[Activity, str]]:
    """按读取范围查活动列表，返回 (活动, 所有者展示名) 行。

    search 模糊匹配标题与地点；from_time 只取该时刻之后的活动（待办聚合用）；
    contact_id 只取该联系人作为参与者的活动（联系人往来 Tab 用）。
    """
    stmt = (
        select(Activity, User.display_name.label("owner_display_name"))
        .join(User, User.id == Activity.owner_user_id)
        .where(Activity.is_active.is_(True), readable_condition(Activity, user))
    )
    if contact_id is not None:
        stmt = stmt.join(
            ActivityParticipant, ActivityParticipant.activity_id == Activity.id
        ).where(ActivityParticipant.contact_id == contact_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Activity.title.ilike(pattern) | Activity.location.ilike(pattern))
    if from_time is not None:
        stmt = stmt.where(Activity.occurred_at >= from_time)
    stmt = stmt.order_by(Activity.occurred_at.desc().nulls_last(), Activity.id.desc())
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    return list((await db.execute(stmt)).all())


async def find_contact_activities(
    db: AsyncSession, user, *, contact_id: int
) -> list[tuple[Activity, str]]:
    """取联系人（作为参与者）的全部活动（时间降序，时间线数据源）。

    关联经 activity_participants（一对多参与者模型）。
    """
    stmt = (
        select(Activity, User.display_name.label("owner_display_name"))
        .join(User, User.id == Activity.owner_user_id)
        .join(ActivityParticipant, ActivityParticipant.activity_id == Activity.id)
        .where(
            ActivityParticipant.contact_id == contact_id,
            Activity.is_active.is_(True),
            readable_condition(Activity, user),
        )
        .order_by(Activity.occurred_at.desc(), Activity.id.desc())
    )
    return list((await db.execute(stmt)).all())


async def get_readable_activity(db: AsyncSession, user, activity_id: int) -> Activity | None:
    """按 id 取当前用户可读的活动；不可见一律 None（上层转 404）。"""
    stmt = select(Activity).where(
        Activity.id == activity_id,
        Activity.is_active.is_(True),
        readable_condition(Activity, user),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_participant_ids(
    db: AsyncSession, user, activity_id: int
) -> list[int]:
    """取活动参与者中当前用户可读的联系人 id（不可读的参与者直接隐藏，D7）。"""
    stmt = (
        select(ActivityParticipant.contact_id)
        .join(Contact, Contact.id == ActivityParticipant.contact_id)
        .where(ActivityParticipant.activity_id == activity_id, readable_condition(Contact, user))
        .order_by(ActivityParticipant.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def replace_participants(
    db: AsyncSession, activity_id: int, contact_ids: list[int]
) -> None:
    """全量替换活动参与者名单（先清后插；调用方负责可读性校验）。"""
    await db.execute(
        ActivityParticipant.__table__.delete().where(
            ActivityParticipant.activity_id == activity_id
        )
    )
    for contact_id in contact_ids:
        db.add(ActivityParticipant(activity_id=activity_id, contact_id=contact_id))
    await db.flush()


async def find_readable_tasks(
    db: AsyncSession,
    user,
    *,
    status: str | None = None,
) -> list[tuple[Task, str]]:
    """按读取范围查任务列表：有截止时间的在前升序，无截止时间的排最后。

    status 过滤当前用户界面的主要诉求（待办/已完成），后端直查不做客户端过滤。
    """
    stmt = (
        select(Task, User.display_name.label("owner_display_name"))
        .join(User, User.id == Task.owner_user_id)
        .where(readable_condition(Task, user))
    )
    if status is not None:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.id.desc())
    return list((await db.execute(stmt)).all())


async def get_readable_task(db: AsyncSession, user, task_id: int) -> Task | None:
    """按 id 取当前用户可读的任务；不可见一律 None（上层转 404）。"""
    stmt = select(Task).where(Task.id == task_id, readable_condition(Task, user))
    return (await db.execute(stmt)).scalar_one_or_none()


def contact_readable_condition(user) -> ColumnElement[bool]:
    """暴露联系人可读条件（供 service 校验参与者可读性，避免 service 摸 Contact 细节）。"""
    return readable_condition(Contact, user)


async def filter_readable_contact_ids(
    db: AsyncSession, user, contact_ids: list[int]
) -> set[int]:
    """从给定 id 中筛出当前用户可读的联系人 id 集合（参与者校验用）。"""
    if not contact_ids:
        return set()
    stmt = select(Contact.id).where(Contact.id.in_(contact_ids), readable_condition(Contact, user))
    return set((await db.execute(stmt)).scalars().all())


async def get_image(db: AsyncSession, image_id: int) -> ActivityImage | None:
    """按 id 取图片行（不含判权；判权由 service 依所属活动完成）。"""
    stmt = select(ActivityImage).where(ActivityImage.id == image_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_images(db: AsyncSession, activity_id: int) -> list[ActivityImage]:
    """取活动的全部图片，按展示顺序升序（最小 sort_order 即时间线封面）。"""
    stmt = (
        select(ActivityImage)
        .where(ActivityImage.activity_id == activity_id)
        .order_by(ActivityImage.sort_order, ActivityImage.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_images_for_activities(
    db: AsyncSession, activity_ids: list[int]
) -> dict[int, list[ActivityImage]]:
    """批量取多个活动的图片并按活动分组（列表接口避免 N+1 查询）。"""
    if not activity_ids:
        return {}
    stmt = (
        select(ActivityImage)
        .where(ActivityImage.activity_id.in_(activity_ids))
        .order_by(ActivityImage.sort_order, ActivityImage.id)
    )
    grouped: dict[int, list[ActivityImage]] = {}
    for image in (await db.execute(stmt)).scalars().all():
        grouped.setdefault(image.activity_id, []).append(image)
    return grouped


async def count_readable_activities(
    db: AsyncSession, user, *, search: str | None = None, contact_id: int | None = None
) -> int:
    """统计可读活动总数（过滤条件必须与 find_readable_activities 保持一致）。"""
    stmt = (
        select(func.count())
        .select_from(Activity)
        .where(Activity.is_active.is_(True), readable_condition(Activity, user))
    )
    if contact_id is not None:
        stmt = stmt.join(
            ActivityParticipant, ActivityParticipant.activity_id == Activity.id
        ).where(ActivityParticipant.contact_id == contact_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(Activity.title.ilike(pattern) | Activity.location.ilike(pattern))
    return (await db.execute(stmt)).scalar_one()
