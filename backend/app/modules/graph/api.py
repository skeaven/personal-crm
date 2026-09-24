"""graph 模块 API：关系类型字典、关系边、图数据端点。"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.graph import service as graph_service
from app.modules.graph.schemas import (
    GraphDataOut,
    KinshipOut,
    RelationshipCreate,
    RelationshipOut,
    RelationshipTypeCreate,
    RelationshipTypeOut,
)

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/relationship-types", response_model=list[RelationshipTypeOut])
async def list_relationship_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RelationshipTypeOut]:
    """关系类型字典（全局共享；按组与排序键稳定排序）。"""
    return await graph_service.list_relationship_types(db)


@router.post("/relationship-types", response_model=RelationshipTypeOut, status_code=201)
async def create_relationship_type(
    body: RelationshipTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RelationshipTypeOut:
    """新增自定义关系类型（正向标签重复返回 409）。"""
    return await graph_service.create_relationship_type(db, current_user, body)


@router.get("/kinship", response_model=KinshipOut)
async def get_kinship(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KinshipOut:
    """从"我"到目标联系人的称谓推导（D15）：最短角色路径 + 中文称呼 + 辈分差。"""
    return await graph_service.kinship_of(db, current_user, contact_id)


@router.get("/data", response_model=GraphDataOut)
async def get_graph_data(
    center_id: int | None = Query(default=None, description="中心联系人（缺省为全图）"),
    depth: int = Query(default=2, ge=1, le=5, description="展开深度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GraphDataOut:
    """图数据（nodes + links）：主页预留区与图谱页共用，按可读范围过滤。"""
    return await graph_service.get_graph_data(db, current_user, center_id=center_id, depth=depth)


@router.get("/relationships", response_model=list[RelationshipOut])
async def list_relationships(
    contact_id: int = Query(description="视角联系人 id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RelationshipOut]:
    """某联系人的关系列表（双向归一：方向与标签按视角计算）。"""
    return await graph_service.list_relationships_of_contact(db, current_user, contact_id)


@router.post("/relationships", response_model=RelationshipOut, status_code=201)
async def create_relationship(
    body: RelationshipCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RelationshipOut:
    """创建关系边（两端须可读，重复返回 409）。"""
    return await graph_service.create_relationship(db, current_user, body)


@router.delete("/relationships/{edge_id}", status_code=204)
async def delete_relationship(
    edge_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除关系边（仅所有者）。"""
    await graph_service.delete_relationship(db, current_user, edge_id)
    return Response(status_code=204)
