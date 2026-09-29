"""auth 模块个人访问令牌：签发、列示、吊销、校验（D11 外部客户端接入）。

- 明文只在签发响应里出现一次，库里只存 sha256（令牌本身高熵，无需 bcrypt 这类慢哈希）；
- 吊销是软删（revoked_at），保留审计痕迹；
- 校验在 /mcp 门卫层完成，工具执行以该令牌所属用户身份进行（D7）。
"""

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.auth.models import User, UserToken
from app.modules.auth.service import get_user_by_id

# 明文前缀：让人一眼看出这是个人名册的令牌（也用于快速排除无关 Bearer）
TOKEN_PREFIX = "crm_"


def hash_token(plain: str) -> str:
    """令牌哈希（sha256 十六进制），存储与校验共用同一实现。"""
    return hashlib.sha256(plain.encode()).hexdigest()


async def issue(db: AsyncSession, user: User, name: str) -> tuple[str, UserToken]:
    """签发令牌，返回 (明文, 记录)；明文此后不再可得。"""
    plain = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    token = UserToken(user_id=user.id, name=name.strip(), token_hash=hash_token(plain))
    db.add(token)
    await db.flush()
    await db.refresh(token)
    return plain, token


async def list_for_user(db: AsyncSession, user: User) -> list[UserToken]:
    """列出本人未吊销的令牌，按签发时间倒序。"""
    stmt = (
        select(UserToken)
        .where(UserToken.user_id == user.id, UserToken.revoked_at.is_(None))
        .order_by(UserToken.created_at.desc(), UserToken.id.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def revoke(db: AsyncSession, user: User, token_id: int) -> None:
    """吊销本人令牌；不存在或不属于本人一律 404（不泄露存在性）。"""
    stmt = select(UserToken).where(
        UserToken.id == token_id,
        UserToken.user_id == user.id,
        UserToken.revoked_at.is_(None),
    )
    token = (await db.execute(stmt)).scalar_one_or_none()
    if token is None:
        raise NotFoundError("令牌不存在")
    token.revoked_at = datetime.now(UTC)


async def resolve(db: AsyncSession, plain: str) -> User | None:
    """按明文令牌取所属用户；未命中/已吊销/账号停用一律 None。

    命中即刷新 last_used_at（用户据此判断哪个令牌还在生效）。
    """
    if not plain.startswith(TOKEN_PREFIX):
        return None
    stmt = select(UserToken).where(
        UserToken.token_hash == hash_token(plain), UserToken.revoked_at.is_(None)
    )
    token = (await db.execute(stmt)).scalar_one_or_none()
    if token is None:
        return None
    user = await get_user_by_id(db, token.user_id)
    if user is None:  # 账号已停用：令牌立即失效
        return None
    token.last_used_at = datetime.now(UTC)
    return user
