"""reminders 模块调度器：进程内 asyncio 后台扫描（D22）。

NAS 友好的最简形态：不引 celery/APScheduler；lifespan 启动任务，1 小时一轮，
启动即扫一轮。扫描开独立会话、异常吞掉记日志——调度器的任何故障都不影响主服务。
"""

import asyncio
import logging
from datetime import timedelta

from app.core.db import get_engine

logger = logging.getLogger(__name__)

# 扫描间隔：个人量级下提醒的时效性以小时计足够（到期日粒度本就是"天"）
SCAN_INTERVAL = timedelta(hours=1)


async def _scan_all_users_once() -> None:
    """对所有用户各做一次提醒扫描（权限口径按用户，与 REST 完全一致）。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.auth.models import User
    from app.modules.reminders import service as reminder_service

    engine = get_engine()
    async with AsyncSession(engine) as db:
        users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
        total_created = 0
        for user in users:
            try:
                stats = await reminder_service.scan_user(db, user)
                total_created += stats.created
            except Exception:  # noqa: BLE001 单用户失败不阻断其他用户
                logger.exception("提醒扫描失败：user_id=%s", user.id)
        await db.commit()
        if total_created:
            logger.info("提醒扫描完成：新增 %d 条（%d 用户）", total_created, len(users))


async def _loop() -> None:
    """扫描循环：启动即扫一次，之后每 SCAN_INTERVAL 一轮，直到被取消。"""
    while True:
        try:
            await _scan_all_users_once()
        except Exception:  # noqa: BLE001 调度循环自身的兜底
            logger.exception("提醒扫描循环异常（不影响主服务）")
        await asyncio.sleep(SCAN_INTERVAL.total_seconds())


def start() -> asyncio.Task:
    """启动后台扫描任务（lifespan 调用）。"""
    return asyncio.create_task(_loop(), name="reminder-scanner")


async def stop(task: asyncio.Task) -> None:
    """停止后台扫描任务（lifespan 关闭时）。"""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
