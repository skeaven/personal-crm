"""测试公共夹具：测试库准备、应用客户端、造数与登录助手。"""

import os
from collections.abc import AsyncIterator

# 必须在导入 app 之前设置环境（覆盖 backend/.env 的开发默认值）
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://crm:crm@127.0.0.1:5433/personal_crm_test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DEBUG", "false")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: E402
    create_async_engine,  # noqa: E402
)

import app.models  # noqa: F401,E402  注册全部模型
from app.core.db import Base  # noqa: E402

TEST_DB_URL = os.environ["DATABASE_URL"]
ADMIN_DB_URL = "postgresql+asyncpg://crm:crm@127.0.0.1:5433/postgres"


@pytest.fixture(scope="session", autouse=True)
async def _prepare_test_database() -> AsyncIterator[None]:
    """会话级准备：确保测试库存在并建全表结构。"""
    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(text("CREATE DATABASE personal_crm_test"))
    except Exception:
        pass  # 库已存在
    finally:
        await admin_engine.dispose()

    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        # pgvector 扩展（embeddings 表依赖；create_all 不会创建扩展）
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """每个测试前清空业务表，保证用例互不干扰。"""
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    await engine.dispose()
    yield


@pytest.fixture(autouse=True)
async def _reset_engine_cache() -> AsyncIterator[None]:
    """每个测试结束后销毁应用引擎缓存。

    pytest-asyncio 默认每个测试用独立事件循环，而 app.core.db 的引擎/会话工厂
    是模块级缓存；不重置的话第二个测试会拿到绑在旧循环上的连接池。
    """
    yield
    import app.core.db as app_db

    if app_db._engine is not None:
        await app_db._engine.dispose()
    app_db._engine = None
    app_db._session_factory = None


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """应用测试客户端（ASGI 直连，不占端口）。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """独立数据库会话：供工具注册表等服务层直测（绕过 HTTP 层）。"""
    from app.core.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture
async def make_user():
    """造数助手：创建家庭+用户并返回 (User, 明文密码)。可多次调用造不同用户。"""
    from tests.factories import create_family_user

    return create_family_user


@pytest.fixture
async def login_headers(client: AsyncClient, make_user):
    """登录助手：造用户并返回该用户的 Authorization 头。"""
    from tests.factories import login_as

    async def _headers(username: str, password: str) -> dict[str, str]:
        return await login_as(client, username, password)

    return _headers


@pytest.fixture
async def checkpointer(monkeypatch):
    """把 runner 的 checkpointer 指到一个测试专用的内存实例。"""
    from langgraph.checkpoint.memory import InMemorySaver

    import agent.runner as runner

    instance = InMemorySaver()
    runner.set_checkpointer(instance)
    yield instance
    runner._CHECKPOINTER = None
