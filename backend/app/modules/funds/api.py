"""funds 模块 API：资金往来端点。"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.funds import service as funds_service
from app.modules.funds.schemas import FundFlowCreate, FundFlowOut, FundFlowUpdate

router = APIRouter(prefix="/funds", tags=["funds"])


@router.get("", response_model=list[FundFlowOut])
async def list_fund_flows(
    response: Response,
    search: str | None = None,
    direction: str | None = Query(default=None, description="out/in"),
    category: str | None = Query(default=None, description="loan/repayment/gift_money/other"),
    status: str | None = Query(default=None, description="pending/settled"),
    contact_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=200, description="每页条数（上限 200）"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FundFlowOut]:
    """资金流水列表：多维过滤组合；总数走 X-Total-Count 头。

    status=pending 时按应还日升序（快到期在前）。
    """
    total = await funds_service.count_fund_flows(
        db,
        current_user,
        search=search,
        direction=direction,
        category=category,
        status=status,
        contact_id=contact_id,
    )
    response.headers["X-Total-Count"] = str(total)
    return await funds_service.list_fund_flows(
        db,
        current_user,
        search=search,
        direction=direction,
        category=category,
        status=status,
        contact_id=contact_id,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=FundFlowOut)
async def create_fund_flow(
    body: FundFlowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FundFlowOut:
    """创建资金流水：带应还日自动置 pending。"""
    return await funds_service.create_fund_flow(db, current_user, body)


@router.get("/{fund_id}", response_model=FundFlowOut)
async def get_fund_flow(
    fund_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FundFlowOut:
    """资金流水详情。"""
    return await funds_service.get_fund_flow(db, current_user, fund_id)


@router.patch("/{fund_id}", response_model=FundFlowOut)
async def update_fund_flow(
    fund_id: int,
    body: FundFlowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FundFlowOut:
    """更新资金流水（仅所有者）；结清流转自动维护 settled_at。"""
    return await funds_service.update_fund_flow(db, current_user, fund_id, body)


@router.delete("/{fund_id}", status_code=204)
async def delete_fund_flow(
    fund_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除资金流水（仅所有者）。"""
    await funds_service.delete_fund_flow(db, current_user, fund_id)
    return Response(status_code=204)
