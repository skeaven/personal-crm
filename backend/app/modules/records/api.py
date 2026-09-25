"""records 模块 API：活动（含参与者）与任务端点。"""

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.records import service as records_service
from app.modules.records.schemas import (
    ActivityCreate,
    ActivityOut,
    ActivityUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services import storage

router = APIRouter(prefix="/records", tags=["records"])


@router.get("/activities", response_model=list[ActivityOut])
async def list_activities(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityOut]:
    """活动列表（新→旧），支持标题/地点关键字搜索；参与者按查看者可读性过滤。"""
    return await records_service.list_activities(db, current_user, search=search)


@router.post("/activities", response_model=ActivityOut)
async def create_activity(
    body: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityOut:
    """创建活动（参与者须全部对创建者可读）。"""
    return await records_service.create_activity(db, current_user, body)


@router.get("/activities/images/{image_id}")
async def read_activity_image(
    image_id: int,
    size: str = Query(default="full", description="thumb/full"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """按活动可见性鉴权后返回图片文件（需登录态，不做静态挂载）。

    路由必须注册在 /activities/{activity_id} 之前，否则 "images" 会被当成 activity_id。
    """
    relative_path = await records_service.get_activity_image_path(
        db, current_user, image_id, thumb=(size == "thumb")
    )
    path = storage.resolve_within_root(relative_path)
    if not path.is_file():
        raise NotFoundError("图片不存在")
    return FileResponse(path)


@router.get("/activities/{activity_id}", response_model=ActivityOut)
async def get_activity(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityOut:
    """活动详情。"""
    return await records_service.get_activity(db, current_user, activity_id)


@router.patch("/activities/{activity_id}", response_model=ActivityOut)
async def update_activity(
    activity_id: int,
    body: ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityOut:
    """更新活动（仅所有者）；participant_ids 提交即全量替换。"""
    return await records_service.update_activity(db, current_user, activity_id, body)


@router.delete("/activities/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除活动（仅所有者，参与者关联级联清理）。"""
    await records_service.delete_activity(db, current_user, activity_id)
    return Response(status_code=204)


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = Query(default=None, description="todo/done/cancelled"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskOut]:
    """任务列表：有截止时间的在前，无截止时间的排最后。"""
    return await records_service.list_tasks(db, current_user, status=status)


@router.post("/tasks", response_model=TaskOut)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskOut:
    """创建任务。"""
    return await records_service.create_task(db, current_user, body)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskOut:
    """任务详情。"""
    return await records_service.get_task(db, current_user, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskOut:
    """更新任务（仅所有者）；status=done 由服务端盖 completed_at。"""
    return await records_service.update_task(db, current_user, task_id, body)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除任务（仅所有者）。"""
    await records_service.delete_task(db, current_user, task_id)
    return Response(status_code=204)
