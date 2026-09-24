"""auth 模块服务层：认证与用户查询，供本模块 API 与其他模块复用。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.core.security import verify_password
from app.modules.auth.models import User
from app.modules.contacts import repository as contact_repo


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """按登录名查用户（用户名统一小写比较）。"""
    stmt = select(User).where(User.username == username.strip().lower())
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """按 id 查用户，停用账号视为不存在。"""
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    return (await db.execute(stmt)).scalar_one_or_none()


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    """校验用户名密码；任一环节不通过返回 None，不区分错误原因。"""
    user = await get_user_by_username(db, username)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def update_me(db: AsyncSession, user: User, contact_id: int | None) -> User:
    """绑定/解绑"我是谁"（D15）：联系人须对当前用户可读且在册。

    绑定后该账号作为关系图视角起点（称谓推导）；解绑不影响历史数据。
    """
    if contact_id is not None:
        contact = await contact_repo.get_readable_contact(db, user, contact_id)
        if contact is None or contact.status != "active":
            raise ValidationError("绑定的联系人不存在或不可见")
    user.contact_id = contact_id
    await db.flush()
    await db.refresh(user)
    return user
