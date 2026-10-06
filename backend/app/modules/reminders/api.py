"""reminders 模块 API：应用内提醒的读取/已读/手动扫描（D22）。"""

from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.reminders import service as reminder_service
from app.modules.reminders.models import Reminder

router = APIRouter(prefix="/reminders", tags=["reminders"])


class ReminderOut(BaseModel):
    """提醒输出：点击跳转用 source+ref_id/contact_id，徽标用 read_at。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    ref_id: int
    due_date: date
    days_left: int
    title: str
    contact_id: int | None
    read_at: datetime | None
    created_at: datetime


class ScanOut(BaseModel):
    """手动扫描统计（设置/调试用）。"""

    created: int
    refreshed: int
    removed: int
    sources: dict[str, int]


@router.get("", response_model=list[ReminderOut])
async def list_reminders(
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Reminder]:
    """当前用户的提醒列表（unread_only=true 只看未读）。"""
    return await reminder_service.list_reminders(db, current_user, unread_only=unread_only)


@router.get("/unread-count", response_model=int)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> int:
    """未读数（铃铛徽标轮询）。"""
    return await reminder_service.unread_count(db, current_user)


@router.post("/read-all", response_model=int)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> int:
    """全部已读；返回影响的条数。"""
    return await reminder_service.mark_all_read(db, current_user)


@router.post("/{reminder_id}/read", status_code=204)
async def mark_read(
    reminder_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """标记单条已读（他人 id 按 404 处理）。"""
    await reminder_service.mark_read(db, current_user, reminder_id)


@router.post("/scan", response_model=ScanOut)
async def trigger_scan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanOut:
    """手动触发当前用户的提醒扫描（幂等，供测试与即时刷新）。"""
    stats = await reminder_service.scan_user(db, current_user)
    return ScanOut(
        created=stats.created,
        refreshed=stats.refreshed,
        removed=stats.removed,
        sources=stats.sources,
    )
