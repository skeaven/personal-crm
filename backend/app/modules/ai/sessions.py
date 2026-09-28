"""ai 模块的会话索引与会话业务：列表、删除、历史、首轮 upsert。

与 ai 模块其他文件一致（pending.py / semantic.py）：一个功能一个文件，
内含数据访问与业务，不套 repository/service 三层。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.ai.models import AiSession
from app.modules.auth.models import User

# 会话标题长度：够在列表里认出是哪次对话即可
TITLE_LIMIT = 30


def make_title(message: str) -> str:
    """取首条用户消息的前若干字作为会话标题（压掉换行，避免列表被撑开）。"""
    return " ".join(message.split())[:TITLE_LIMIT] or "新对话"


async def list_sessions(db: AsyncSession, user: User) -> list[AiSession]:
    """列出当前用户的会话，按最后活跃倒序。"""
    stmt = (
        select(AiSession)
        .where(AiSession.user_id == user.id)
        .order_by(AiSession.updated_at.desc(), AiSession.session_id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_owned_session(db: AsyncSession, user: User, session_id: str) -> AiSession:
    """取当前用户拥有的会话；不存在或不属于本人一律 404（不泄露存在性）。"""
    stmt = select(AiSession).where(
        AiSession.session_id == session_id, AiSession.user_id == user.id
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None:
        raise NotFoundError("会话不存在")
    return session


async def ensure_session(db: AsyncSession, user: User, session_id: str, first_message: str) -> None:
    """首轮提问时建立会话索引行（已存在则不动，只更新活跃时间）。

    没有单独的「创建会话」端点——少一个接口、少一次往返。
    """
    existing = await db.get(AiSession, session_id)
    if existing is not None:
        if existing.user_id != user.id:
            # 主键撞车说明前端生成的 id 不属于本人：按不可用处理，不泄露他人会话
            raise NotFoundError("会话不存在")
        existing.updated_at = func.now()
        return
    db.add(AiSession(session_id=session_id, user_id=user.id, title=make_title(first_message)))


async def delete_session(db: AsyncSession, user: User, session_id: str) -> None:
    """删除会话索引行（对话内容由调用方经 checkpointer 清）。"""
    session = await get_owned_session(db, user, session_id)
    await db.delete(session)


async def get_history(db: AsyncSession, user: User, session_id: str) -> list[dict]:
    """读取会话历史：先校验归属，再取 checkpointer 里的消息。"""
    from agent.runner import load_history

    await get_owned_session(db, user, session_id)
    return await load_history(session_id, user.id)