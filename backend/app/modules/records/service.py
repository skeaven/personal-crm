"""records 模块服务层：活动（参与者语义）与任务的业务规则。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.records import repository as records_repo
from app.modules.records.models import Activity, Task
from app.modules.records.schemas import (
    ActivityCreate,
    ActivityOut,
    ActivityUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services.permission import ensure_can_write


def _activity_to_out(
    activity: Activity, owner_display_name: str, participant_ids: list[int]
) -> ActivityOut:
    """组装活动输出契约：参与者 id 列表由调用方按可读性过滤后传入。"""
    activity.owner_display_name = owner_display_name
    payload = ActivityOut.model_validate(activity)
    payload.participant_ids = participant_ids
    return payload


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
    return _activity_to_out(activity, user.display_name, data.participant_ids)


async def list_activities(
    db: AsyncSession, user: User, *, search: str | None
) -> list[ActivityOut]:
    """列出可读活动，参与者名单按查看者可读性过滤后回显。"""
    rows = await records_repo.find_readable_activities(db, user, search=search)
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(_activity_to_out(activity, owner_name, ids))
    return outputs


async def list_upcoming_activities(
    db: AsyncSession, user: User, *, from_time: datetime
) -> list[ActivityOut]:
    """列出该时刻之后的活动（待办聚合用；过去活动是历史，不属于任何待办桶）。"""
    rows = await records_repo.find_readable_activities(db, user, from_time=from_time)
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(_activity_to_out(activity, owner_name, ids))
    return outputs


async def list_contact_activities(
    db: AsyncSession, user: User, *, contact_id: int
) -> list[ActivityOut]:
    """联系人活动时间线源（作为参与者的活动，全量、时间降序；归并由聚合层完成）。"""
    rows = await records_repo.find_contact_activities(db, user, contact_id=contact_id)
    outputs: list[ActivityOut] = []
    for activity, owner_name in rows:
        ids = await records_repo.list_participant_ids(db, user, activity.id)
        outputs.append(_activity_to_out(activity, owner_name, ids))
    return outputs


async def get_activity(db: AsyncSession, user: User, activity_id: int) -> ActivityOut:
    """读取活动详情；不可见按 404 处理。"""
    activity = await records_repo.get_readable_activity(db, user, activity_id)
    if activity is None:
        raise NotFoundError("活动不存在")
    owner = await db.get(User, activity.owner_user_id)
    ids = await records_repo.list_participant_ids(db, user, activity.id)
    return _activity_to_out(activity, owner.display_name if owner else "未知", ids)


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

    updates = data.model_dump(exclude={"participant_ids"}, exclude_unset=True)
    for field, value in updates.items():
        setattr(activity, field, value)
    await db.flush()
    await db.refresh(activity)

    if "participant_ids" in data.model_fields_set:
        await records_repo.replace_participants(db, activity.id, data.participant_ids)

    ids = await records_repo.list_participant_ids(db, user, activity.id)
    return _activity_to_out(activity, user.display_name, ids)


async def delete_activity(db: AsyncSession, user: User, activity_id: int) -> None:
    """删除活动（仅所有者）；参与者行随活动级联清理。"""
    activity = await records_repo.get_readable_activity(db, user, activity_id)
    if activity is None:
        raise NotFoundError("活动不存在")
    ensure_can_write(user, activity)
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
