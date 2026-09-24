"""数据库引擎、会话工厂与 ORM 声明基类。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """全项目唯一的 ORM 声明基类，Alembic 以它的 metadata 为准。"""


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """懒创建全局异步引擎（延迟到首次使用，便于测试前覆盖环境变量）。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """懒创建会话工厂；expire_on_commit=False 以便提交后仍可读取属性。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每请求一个会话；请求成功统一提交，异常统一回滚。

    服务层只做 flush 不做 commit，保证"一个请求一个事务"的边界清晰。
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
