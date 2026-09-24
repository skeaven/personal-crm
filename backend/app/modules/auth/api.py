"""auth 模块 API：登录与当前用户信息。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import UnauthorizedError
from app.core.security import create_access_token
from app.modules.auth.models import User
from app.modules.auth.schemas import LoginRequest, LoginResponse, MeUpdate, UserOut
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
