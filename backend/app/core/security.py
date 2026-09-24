"""安全原语：密码哈希（pwdlib/bcrypt）与 JWT 签发校验（pyjwt）。"""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings

# 明确指定 bcrypt（已装 extra）；不使用 recommended() 以免隐式依赖 argon2
_password_hasher = PasswordHash((BcryptHasher(),))


def hash_password(plain: str) -> str:
    """对明文密码做哈希，返回可存储的哈希串。"""
    return _password_hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    """校验明文密码与存储哈希是否匹配。"""
    return _password_hasher.verify(plain, password_hash)


def create_access_token(user_id: int) -> str:
    """为指定用户签发 JWT，subject 存用户 id。"""
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """解析 JWT 并返回用户 id；无效或过期抛 jwt.InvalidTokenError。"""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return int(payload["sub"])
