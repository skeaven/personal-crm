"""records 模块服务层：活动（参与者语义）与任务的业务规则。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.records import repository as records_repo
from app.modules.records.models import Activity, ActivityImage, Task
from app.modules.records.schemas import (
    ActivityCreate,
    ActivityImageOut,
    ActivityOut,
    ActivityUpdate,
    ImageRefIn,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services import storage
from app.services.permission import ensure_can_write


def _activity_to_out(
    activity: Activity,
    owner_display_name: str,
    participant_ids: list[int],
    images: list[ActivityImage],
) -> ActivityOut:
    """组装活动输出契约：参与者与图片均由调用方查好（可读性/顺序）后传入。"""
    activity.owner_display_name = owner_display_name
    payload = ActivityOut.model_validate(activity)
    payload.participant_ids = participant_ids
    payload.images = [ActivityImageOut.model_validate(image) for image in images]
    return payload


async def _replace_images(
    db: AsyncSession, user: User, activity_id: int, refs: list[ImageRefIn]
) -> list[ActivityImage]:
    """按全量替换语义落图片：refs 顺序即 sort_order，未出现的旧图连同文件删除。

    先做全部纯校验再动盘——否则中途发现非法项时，前面的临时文件已被移走。
    """
    existing = {image.id: image for image in await records_repo.list_images(db, activity_id)}

    for ref in refs:
        if ref.id is not None and ref.id not in existing:
            raise ValidationError("存在不属于本活动的图片")
        if ref.temp_path is not None and not storage.is_own_temp_path(ref.temp_path, user.id):
            raise ValidationError("非法的临时文件路径")

    kept_ids: set[int] = set()
    for order, ref in enumerate(refs):
        if ref.id is not None:
            existing[ref.id].sort_order = order
            kept_ids.add(ref.id)
        else:
            full_path, thumb_path = storage.promote_temp(ref.temp_path, user.id, "activities")
            db.add(
                ActivityImage(
                    activity_id=activity_id,
                    path=full_path,
                    thumb_path=thumb_path,
                    sort_order=order,
                )
            )

    removed_paths: list[str] = []
    for image_id, image in existing.items():
        if image_id in kept_ids:
            continue
        removed_paths.extend([image.path, image.thumb_path])
        await db.delete(image)
    storage.defer_delete(db, *removed_paths)

    await db.flush()
    return await records_repo.list_images(db, activity_id)


async def create_activity(
    db: AsyncSession, user: User, data: ActivityCreate
) -> ActivityOut:
    """创建活动并挂参与者；参与者必须全部对创建者可读，否则整体拒绝（不落半截数据）。"""
    readable_ids = await records_repo.filter_readable_contact_ids(
        db, user, data.participant_ids
    )
    missing = set(data.participant_ids) - readable_ids
    if missing:
        raise ValidationError("存在不可见的参与者联系人，请检查后重试")

    activity = Activity(
        title=data.title,
        occurred_at=data.occurred_at,
        location=data.location,
        detail=data.detail,
        owner_user_id=user.id,
        family_id=user.family_id,
    )
    db.add(activity)
    await db.flush()
    await records_repo.replace_participants(db, activity.id, data.participant_ids)
    images = await _replace_images(db, user, activity.id, data.images)
    return _activity_to_out(activity, user.display_name, data.participant_ids, images)


async def list_activities(
    db: AsyncSession,
    user: User,
    *,
    search: str | None,
    contact_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[ActivityOut]:
    """列出可读活动；contact_id 用于联系人往来 Tab，limit/offset 用于分页。"""
    rows = await records_repo.find_readable_activities(
        db, user, search=search, contact_id=contact_id, limit=limit, offset=offset
    )
    images_map = await records_repo.list_images_for_activities(
        db, [activity.id for activity, _ in rows]
    )
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(
            _activity_to_out(activity, owner_name, ids, images_map.get(activity.id, []))
        )
    return outputs


async def count_activities(
    db: AsyncSession, user: User, *, search: str | None, contact_id: int | None = None
) -> int:
    """可读活动总数（分页响应头 X-Total-Count 用）。"""
    return await records_repo.count_readable_activities(
        db, user, search=search, contact_id=contact_id
    )


async def list_upcoming_activities(
    db: AsyncSession, user: User, *, from_time: datetime
) -> list[ActivityOut]:
    """列出该时刻之后的活动（待办聚合用；过去活动是历史，不属于任何待办桶）。"""
    rows = await records_repo.find_readable_activities(db, user, from_time=from_time)
    images_map = await records_repo.list_images_for_activities(
        db, [activity.id for activity, _ in rows]
    )
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(
            _activity_to_out(activity, owner_name, ids, images_map.get(activity.id, []))
        )
    return outputs


async def list_contact_activities(
    db: AsyncSession, user: User, *, contact_id: int
) -> list[ActivityOut]:
    """联系人活动时间线源（作为参与者的活动，全量、时间降序；归并由聚合层完成）。"""
    rows = await records_repo.find_contact_activities(db, user, contact_id=contact_id)
    images_map = await records_repo.list_images_for_activities(
        db, [activity.id for activity, _ in rows]
    )
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(
            _activity_to_out(activity, owner_name, ids, images_map.get(activity.id, []))
        )
    return outputs


async def get_activity(db: AsyncSession, user: User, activity_id: int) -> ActivityOut:
    """读取活动详情；不可见按 404 处理。"""
    activity = await records_repo.get_readable_activity(db, user, activity_id)
    if activity is None:
        raise NotFoundError("活动不存在")
    owner = await db.get(User, activity.owner_user_id)
    ids = await records_repo.list_participant_ids(db, user, activity.id)
    images = await records_repo.list_images(db, activity.id)
    return _activity_to_out(activity, owner.display_name if owner else "未知", ids, images)


async def update_activity(
    db: AsyncSession, user: User, activity_id: int, data: ActivityUpdate
) -> ActivityOut:
    """更新活动（仅所有者）；participant_ids 提交即全量替换，替换前校验可读性。"""
    activity = await records_repo.get_readable_activity(db, user, activity_id)
    if activity is None:
        raise NotFoundError("活动不存在")
    ensure_can_write(user, activity)

    if "participant_ids" in data.model_fields_set:
        readable_ids = await records_repo.filter_readable_contact_ids(
            db, user, data.participant_ids
        )
        missing = set(data.participant_ids) - readable_ids
        if missing:
            raise ValidationError("存在不可见的参与者联系人，请检查后重试")

    updates = data.model_dump(exclude={"participant_ids", "images"}, exclude_unset=True)
    for field, value in updates.items():
        setattr(activity, field, value)
    await db.flush()
    await db.refresh(activity)

    if "participant_ids" in data.model_fields_set:
        await records_repo.replace_participants(db, activity.id, data.participant_ids)
    if data.images is not None:
        await _replace_images(db, user, activity.id, data.images)

    ids = await records_repo.list_participant_ids(db, user, activity.id)
    images = await records_repo.list_images(db, activity.id)
    return _activity_to_out(activity, user.display_name, ids, images)


async def get_activity_image_path(
    db: AsyncSession, user: User, image_id: int, *, thumb: bool
) -> str:
    """取活动图片的相对路径；图片所属活动不可读时按 404 处理。

    返回相对路径而不是绝对路径，落盘细节留给 api 层经 storage 解析。
    """
    image = await records_repo.get_image(db, image_id)
    if image is None:
        raise NotFoundError("图片不存在")
    activity = await records_repo.get_readable_activity(db, user, image.activity_id)
    if activity is None:
        raise NotFoundError("图片不存在")
    return image.thumb_path if thumb else image.path


async def delete_activity(db: AsyncSession, user: User, activity_id: int) -> None:
    """删除活动（仅所有者）；图片行随活动级联删，文件在事务提交成功后删。"""
    activity = await records_repo.get_readable_activity(db, user, activity_id)
    if activity is None:
        raise NotFoundError("活动不存在")
    ensure_can_write(user, activity)

    images = await records_repo.list_images(db, activity_id)
    storage.defer_delete(
        db, *[path for image in images for path in (image.path, image.thumb_path)]
    )
    await db.delete(activity)
    await db.flush()


async def create_task(db: AsyncSession, user: User, data: TaskCreate) -> TaskOut:
    """创建任务；挂了联系人时校验其对创建者可读。"""
    if data.contact_id is not None:
        readable_ids = await records_repo.filter_readable_contact_ids(
            db, user, [data.contact_id]
        )
        if data.contact_id not in readable_ids:
            raise ValidationError("关联的联系人不可见")
    task = Task(**data.model_dump(), owner_user_id=user.id, family_id=user.family_id)
    db.add(task)
    await db.flush()
    task.owner_display_name = user.display_name
    return TaskOut.model_validate(task)


async def list_tasks(
    db: AsyncSession, user: User, *, status: str | None
) -> list[TaskOut]:
    """列出可读任务（有截止时间在前）。"""
    rows = await records_repo.find_readable_tasks(db, user, status=status)
    outputs: list[TaskOut] = []
    for task, owner_name in rows:
        task.owner_display_name = owner_name
        outputs.append(TaskOut.model_validate(task))
    return outputs


async def get_task(db: AsyncSession, user: User, task_id: int) -> TaskOut:
    """读取任务详情；不可见按 404 处理。"""
    task = await records_repo.get_readable_task(db, user, task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    owner = await db.get(User, task.owner_user_id)
    task.owner_display_name = owner.display_name if owner else "未知"
    return TaskOut.model_validate(task)


async def update_task(db: AsyncSession, user: User, task_id: int, data: TaskUpdate) -> TaskOut:
    """更新任务（仅所有者）；status 置 done 时服务端盖 completed_at。"""
    task = await records_repo.get_readable_task(db, user, task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    ensure_can_write(user, task)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(task, field, value)
    if updates.get("status") == "done" and task.completed_at is None:
        task.completed_at = datetime.now(UTC)
    elif "status" in updates and updates["status"] != "done":
        task.completed_at = None
    await db.flush()
    await db.refresh(task)

    task.owner_display_name = user.display_name
    return TaskOut.model_validate(task)


async def delete_task(db: AsyncSession, user: User, task_id: int) -> None:
    """删除任务（仅所有者）。"""
    task = await records_repo.get_readable_task(db, user, task_id)
    if task is None:
        raise NotFoundError("任务不存在")
    ensure_can_write(user, task)
    await db.delete(task)
    await db.flush()
