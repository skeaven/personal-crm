"""auth 模块 API：登录、当前用户信息、个人访问令牌（D11）。"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import UnauthorizedError
from app.core.security import create_access_token
from app.modules.auth import tokens
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    MeUpdate,
    TokenIssueIn,
    TokenIssueOut,
    TokenOut,
    UserOut,
)
from app.modules.auth.service import authenticate, update_me

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    """账号密码登录，签发 JWT；失败统一返回 401，不暴露原因细节。"""
    user = await authenticate(db, body.username, body.password)
    if user is None:
        raise UnauthorizedError("用户名或密码错误")
    token = create_access_token(user.id)
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def read_me(current_user=Depends(get_current_user)) -> UserOut:
    """返回当前登录用户信息，前端用它渲染身份与权限提示。"""
    return UserOut.model_validate(current_user)


@router.put("/me", response_model=UserOut)
async def update_current_user(
    body: MeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """绑定/解绑"我是谁"（D15）：关系图视角推导以该联系人为起点。"""
    await update_me(db, current_user, body.contact_id)
    return UserOut.model_validate(current_user)


@router.post("/tokens", response_model=TokenIssueOut)
async def issue_token(
    body: TokenIssueIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TokenIssueOut:
    """签发个人令牌（D11）：明文只在本响应里出现一次，之后只能吊销重签。"""
    plain, token = await tokens.issue(db, current_user, body.name)
    return TokenIssueOut(**TokenOut.model_validate(token).model_dump(), token=plain)


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TokenOut]:
    """我的令牌列表（不含明文与哈希）。"""
    return [TokenOut.model_validate(row) for row in await tokens.list_for_user(db, current_user)]


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """吊销令牌：立刻失效，记录保留（软删）。"""
    await tokens.revoke(db, current_user, token_id)
    return Response(status_code=204)
