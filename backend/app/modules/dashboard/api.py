"""dashboard 模块 API：待办看板 + 联系人时间线聚合端点。

时间线语义上属于联系人详情页（/contacts/{id}/timeline），但聚合实现在 dashboard
模块（L4 纯消费层）——contacts(L2) 不允许依赖 gifts/funds/records(L3)。
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import ValidationError
from app.modules.auth.models import User
from app.modules.contacts import service as contacts_service
from app.modules.dashboard import service as dashboard_service
from app.modules.dashboard.schemas import (
    TODO_BUCKET_VALUES,
    TimelineOut,
    TodoItemOut,
)
from app.modules.records import service as records_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardStatsOut(BaseModel):
    """主页统计卡数据（口径与名册过滤联动）。"""

    total_contacts: int
    recent_contacted: int
    stale_half_year: int
    open_tasks: int


@router.get("/stats", response_model=DashboardStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardStatsOut:
    """主页统计：联系人总数 / 近 30 天联系 / 半年未联系 / 进行中待办。"""
    stats = await contacts_service.activity_stats(db, current_user)
    open_tasks = await records_service.list_tasks(db, current_user, status="todo")
    return DashboardStatsOut(**stats, open_tasks=len(open_tasks))

# 时间线路由单独挂 /contacts 前缀（聚合实现仍在 dashboard 模块）
timeline_router = APIRouter(prefix="/contacts", tags=["dashboard"])


@timeline_router.get("/{contact_id}/timeline", response_model=TimelineOut)
async def get_contact_timeline(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelineOut:
    """联系人时间线（礼物/资金/活动倒序全量；"动态加载"观感由前端切片渲染实现）。"""
    return await dashboard_service.build_contact_timeline(db, current_user, contact_id)


@router.get("/todos", response_model=list[TodoItemOut])
async def list_todos(
    bucket: str = Query(default="todo", description="todo/overdue/done/all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TodoItemOut]:
    """待办看板：五来源统一视图，按桶过滤（待办/过期/已完成/全部），近的在前。"""
    if bucket not in TODO_BUCKET_VALUES:
        raise ValidationError(f"bucket 必须是 {TODO_BUCKET_VALUES} 之一")
    return await dashboard_service.build_todo_board(db, current_user, bucket)
