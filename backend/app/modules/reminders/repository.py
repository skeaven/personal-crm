"""reminders 模块 repository：幂等重建的数据库操作（D22）。"""

from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reminders.models import Reminder


async def list_existing(
    db: AsyncSession, user_id: int, source: str
) -> dict[tuple[int, date], Reminder]:
    """取某用户某来源的现有提醒，键 = (ref_id, due_date)。"""
    stmt = select(Reminder).where(Reminder.user_id == user_id, Reminder.source == source)
    rows = (await db.execute(stmt)).scalars().all()
    return {(row.ref_id, row.due_date): row for row in rows}


async def upsert(
    db: AsyncSession,
    *,
    user_id: int,
    family_id: int,
    source: str,
    ref_id: int,
    due_date: date,
    days_left: int,
    title: str,
    contact_id: int | None,
) -> bool:
    """幂等写入一条提醒；返回是否新建。

    已存在未读 → 刷新快照（title/days_left/due_date 若业务端变化）；已读 → 不复活。
    """
    stmt = select(Reminder).where(
        Reminder.user_id == user_id,
        Reminder.source == source,
        Reminder.ref_id == ref_id,
        Reminder.due_date == due_date,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        if existing.read_at is None:
            existing.title = title
            existing.days_left = days_left
        return False
    db.add(
        Reminder(
            user_id=user_id,
            family_id=family_id,
            source=source,
            ref_id=ref_id,
            due_date=due_date,
            days_left=days_left,
            title=title,
            contact_id=contact_id,
        )
    )
    return True


async def delete_unread_not_in(
    db: AsyncSession, user_id: int, source: str, keep_keys: set[tuple[int, date]]
) -> int:
    """删除某来源下 (ref_id, due_date) 不在存活键集合内的未读提醒；返回删除数。

    注意按业务键 (ref_id, due_date) 对比，不能用主键 id——两者是不同的 id 空间，
    混用会把上一轮正常生成的提醒误判为"源头消失"而整批误删。
    """
    stmt = delete(Reminder).where(
        Reminder.user_id == user_id,
        Reminder.source == source,
        Reminder.read_at.is_(None),
    )
    if keep_keys:
        stmt = stmt.where(
            tuple_(Reminder.ref_id, Reminder.due_date).not_in(keep_keys)
        )
    result = await db.execute(stmt)
    return result.rowcount or 0


async def list_reminders(db: AsyncSession, user_id: int, *, unread_only: bool) -> list[Reminder]:
    """某用户的提醒列表（未读在前，days_left 升序）。"""
    stmt = select(Reminder).where(Reminder.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Reminder.read_at.is_(None))
    stmt = stmt.order_by(Reminder.read_at.is_(None).desc(), Reminder.days_left, Reminder.id)
    return list((await db.execute(stmt)).scalars().all())


async def unread_count(db: AsyncSession, user_id: int) -> int:
    """某用户未读提醒数（铃铛徽标）。"""
    stmt = select(func.count()).select_from(Reminder).where(
        Reminder.user_id == user_id, Reminder.read_at.is_(None)
    )
    return (await db.execute(stmt)).scalar_one()


async def get_user_reminder(db: AsyncSession, user_id: int, reminder_id: int) -> Reminder | None:
    """按 id 取某用户自己的提醒（他人 id 视为不存在，防越权探测）。"""
    stmt = select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def mark_read(db: AsyncSession, reminder: Reminder) -> None:
    """标记单条已读（幂等：已读再读不动）。"""
    if reminder.read_at is None:
        reminder.read_at = datetime.now(UTC)
        await db.flush()


async def mark_all_read(db: AsyncSession, user_id: int) -> int:
    """全部已读；返回影响的条数。"""
    rows = (await db.execute(
        select(Reminder).where(Reminder.user_id == user_id, Reminder.read_at.is_(None))
    )).scalars().all()
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
    await db.flush()
    return len(rows)
