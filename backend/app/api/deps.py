"""API 公共依赖：数据库会话与当前登录用户。"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import UnauthorizedError
from app.core.security import decode_access_token
from app.modules.auth.models import User
from app.modules.auth.service import get_user_by_id

# auto_error=False 以便自定义 401 错误信息
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Bearer Token 解析当前用户；缺失/无效/停用统一 401。"""
    if credentials is None:
        raise UnauthorizedError("请先登录")
    try:
        user_id = decode_access_token(credentials.credentials)
    except Exception as exc:  # jwt 过期/签名错误统一按未登录处理
        raise UnauthorizedError("登录已失效，请重新登录") from exc
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise UnauthorizedError("账号不存在或已停用")
    return user
