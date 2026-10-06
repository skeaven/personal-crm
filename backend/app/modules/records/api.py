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
    NoteCreate,
    NoteOut,
    NoteUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services import storage

router = APIRouter(prefix="/records", tags=["records"])


@router.get("/activities", response_model=list[ActivityOut])
async def list_activities(
    response: Response,
    search: str | None = None,
    contact_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=200, description="每页条数（上限 200）"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityOut]:
    """活动列表（新→旧）；总数走 X-Total-Count 头，供列表页算页码。"""
    total = await records_service.count_activities(
        db, current_user, search=search, contact_id=contact_id
    )
    response.headers["X-Total-Count"] = str(total)
    return await records_service.list_activities(
        db, current_user, search=search, contact_id=contact_id, limit=limit, offset=offset
    )


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


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(
    contact_id: int = Query(description="按联系人过滤（当前备注必须归属联系人）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NoteOut]:
    """联系人备注列表（新→旧）；联系人不可读时返回空列表。"""
    return await records_service.list_contact_notes(
        db, current_user, contact_id=contact_id
    )


@router.post("/notes", response_model=NoteOut)
async def create_note(
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteOut:
    """创建备注（归属联系人须对创建者可读）。"""
    return await records_service.create_note(db, current_user, body)


@router.get("/notes/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteOut:
    """备注详情。"""
    return await records_service.get_note(db, current_user, note_id)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: int,
    body: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NoteOut:
    """更新备注正文（仅所有者）。"""
    return await records_service.update_note(db, current_user, note_id, body)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除备注（仅所有者）。"""
    await records_service.delete_note(db, current_user, note_id)
    return Response(status_code=204)
