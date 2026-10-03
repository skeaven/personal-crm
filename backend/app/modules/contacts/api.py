"""contacts 模块 API：名册接口（列表/详情/创建/更新/升级/归档/同名检测）。

注意：duplicate-check 必须注册在 /{contact_id} 之前，避免路径参数吞掉它。
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.contacts import service as contact_service
from app.modules.contacts.schemas import (
    ContactCreate,
    ContactCreateResponse,
    ContactDetailOut,
    ContactOut,
    ContactUpdate,
    DuplicateWarning,
    ImportantDateCreate,
    ImportantDateUpdate,
    MapPointsOut,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/duplicate-check", response_model=list[DuplicateWarning])
async def check_duplicate(
    name: str = "",
    nickname: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DuplicateWarning]:
    """输入过程中的实时同名提示（表单失焦时调用）。"""
    return await contact_service.check_duplicates(db, current_user, name, nickname)


@router.get("/schools", response_model=list[str])
async def list_schools(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[str]:
    """毕业院校去重列表（校友查找/表单选择数据源）。"""
    return await contact_service.list_schools(db, current_user)


@router.get("/map-points", response_model=MapPointsOut)
async def get_map_points(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MapPointsOut:
    """地图页数据：可读联系人的坐标撒点 + 省份计数聚合（choropleth，D14）。"""
    return await contact_service.map_points(db, current_user)


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    tier: str | None = None,
    search: str | None = None,
    activity: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ContactOut]:
    """名册列表：可读联系人，支持层级过滤、关键字搜索与"最近联系"口径过滤（主页跳转联动）。"""
    return await contact_service.list_contacts(
        db, current_user, tier=tier, search=search, activity=activity
    )


@router.post("", response_model=ContactCreateResponse)
async def create_contact(
    body: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactCreateResponse:
    """创建联系人：命中同名且未确认时返回 created=false + 提醒列表。"""
    return await contact_service.create_contact(db, current_user, body)


@router.get("/{contact_id}", response_model=ContactDetailOut)
async def get_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactDetailOut:
    """联系人详情（含重要日期区块；时间线/礼物/资金等区块后续增量挂载）。"""
    return await contact_service.get_contact(db, current_user, contact_id)


@router.patch("/{contact_id}", response_model=ContactDetailOut)
async def update_contact(
    contact_id: int,
    body: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactDetailOut:
    """更新联系人（仅所有者可操作）。"""
    return await contact_service.update_contact(db, current_user, contact_id, body)


@router.post("/{contact_id}/promote", response_model=ContactDetailOut)
async def promote_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactDetailOut:
    """边缘联系人一键升级为直接联系人（仅所有者）。"""
    return await contact_service.promote_contact(db, current_user, contact_id)


@router.delete("/{contact_id}", status_code=204)
async def archive_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """归档联系人（软删，仅所有者）。"""
    await contact_service.archive_contact(db, current_user, contact_id)
    return Response(status_code=204)


@router.post("/{contact_id}/dates", response_model=ContactDetailOut)
async def create_date(
    contact_id: int,
    body: ImportantDateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactDetailOut:
    """为联系人创建重要日期（仅所有者），返回更新后的详情。"""
    return await contact_service.create_date(db, current_user, contact_id, body)


@router.patch("/{contact_id}/dates/{date_id}", response_model=ContactDetailOut)
async def update_date(
    contact_id: int,
    date_id: int,
    body: ImportantDateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactDetailOut:
    """更新重要日期（仅所有者），返回更新后的详情。"""
    return await contact_service.update_date(db, current_user, contact_id, date_id, body)


@router.delete("/{contact_id}/dates/{date_id}", status_code=204)
async def delete_date(
    contact_id: int,
    date_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除重要日期（仅所有者）。"""
    await contact_service.delete_date(db, current_user, contact_id, date_id)
    return Response(status_code=204)
