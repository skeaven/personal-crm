"""gifts 模块 API：礼物往来与愿望清单端点。

注意：/wishlist 系字面量子路径，全部注册在 /{gift_id} 之前，避免路径参数吞掉它
（同 contacts/duplicate-check 的处理）。
"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.gifts import service as gifts_service
from app.modules.gifts.schemas import (
    GiftCreate,
    GiftOut,
    GiftUpdate,
    WishlistConvertOut,
    WishlistCreate,
    WishlistOut,
    WishlistUpdate,
)

router = APIRouter(prefix="/gifts", tags=["gifts"])


@router.get("", response_model=list[GiftOut])
async def list_gifts(
    search: str | None = None,
    direction: str | None = Query(default=None, description="given/received"),
    contact_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GiftOut]:
    """礼物往来列表：关键字（名称/场合）、方向、联系人组合过滤。"""
    return await gifts_service.list_gifts(
        db, current_user, search=search, direction=direction, contact_id=contact_id
    )


@router.post("", response_model=GiftOut)
async def create_gift(
    body: GiftCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GiftOut:
    """创建礼物往来记录。"""
    return await gifts_service.create_gift(db, current_user, body)


@router.get("/wishlist", response_model=list[WishlistOut])
async def list_wishlist(
    search: str | None = None,
    status: str | None = Query(default=None, description="open/purchased/given"),
    contact_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WishlistOut]:
    """愿望清单列表：关键字、状态、联系人组合过滤。"""
    return await gifts_service.list_wishlist(
        db, current_user, search=search, status=status, contact_id=contact_id
    )


@router.post("/wishlist", response_model=WishlistOut)
async def create_wishlist_item(
    body: WishlistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistOut:
    """创建愿望清单项。"""
    return await gifts_service.create_wishlist_item(db, current_user, body)


@router.patch("/wishlist/{item_id}", response_model=WishlistOut)
async def update_wishlist_item(
    item_id: int,
    body: WishlistUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistOut:
    """更新愿望（仅所有者）。"""
    return await gifts_service.update_wishlist(db, current_user, item_id, body)


@router.delete("/wishlist/{item_id}", status_code=204)
async def delete_wishlist_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除愿望（仅所有者）。"""
    await gifts_service.delete_wishlist(db, current_user, item_id)
    return Response(status_code=204)


@router.post("/wishlist/{item_id}/convert", response_model=WishlistConvertOut)
async def convert_wishlist_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WishlistConvertOut:
    """愿望送出 → 生成礼物记录并闭环（仅所有者，重复转换返回 400）。"""
    return await gifts_service.convert_wishlist_to_gift(db, current_user, item_id)


@router.get("/{gift_id}", response_model=GiftOut)
async def get_gift(
    gift_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GiftOut:
    """礼物详情。"""
    return await gifts_service.get_gift(db, current_user, gift_id)


@router.patch("/{gift_id}", response_model=GiftOut)
async def update_gift(
    gift_id: int,
    body: GiftUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GiftOut:
    """更新礼物（仅所有者）。"""
    return await gifts_service.update_gift(db, current_user, gift_id, body)


@router.delete("/{gift_id}", status_code=204)
async def delete_gift(
    gift_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除礼物记录（仅所有者）。"""
    await gifts_service.delete_gift(db, current_user, gift_id)
    return Response(status_code=204)
