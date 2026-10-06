"""reminders 模块服务层：三源扫描 + 幂等重建（D22）。

口径不重复实现：重要日期复用 contacts_service.upcoming_date_reminders（含农历/滚动
明年），任务/还款用 records/funds 既有 service 的列表函数按提醒窗口过滤；
活动不进提醒（临近活动主页已可见，避免噪音）。
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.reminders import repository as reminder_repo

# 提醒窗口：到期前 N 天内生成；过期事项持续提醒直到完成/结清
REMINDER_WINDOW_DAYS = 7


@dataclass
class ScanStats:
    """一次扫描的结果统计（手动触发的回显）。"""

    created: int = 0
    refreshed: int = 0
    removed: int = 0
    sources: dict[str, int] = field(default_factory=dict)


def _in_window(due: date, today: date) -> bool:
    """窗口判断：到期日距今 ≤ 窗口（过期为负数也恒在窗口内）。"""
    return (due - today).days <= REMINDER_WINDOW_DAYS


def _when_label(days_left: int) -> str:
    """剩余天数 → 人话（今天到期/还有 N 天/过期 N 天），三源共用。"""
    if days_left == 0:
        return "今天到期"
    if days_left > 0:
        return f"还有 {days_left} 天"
    return f"过期 {-days_left} 天"


def _due_date_of(dt: datetime) -> date:
    """UTC 时刻 → 本地日期（与 dashboard 待办同口径，避免跨时区差一天）。"""
    return dt.astimezone().date()


async def _collect_task_items(db: AsyncSession, user: User, today: date) -> list[tuple]:
    """任务源：未完成且有截止时间、进窗口的 → (source, ref_id, due, title, contact_id)。"""
    from app.modules.records import service as records_service

    items = []
    for task in await records_service.list_tasks(db, user, status="todo"):
        if task.due_at is None:
            continue
        due = _due_date_of(task.due_at)
        if not _in_window(due, today):
            continue
        days_left = (due - today).days
        when = _when_label(days_left)
        title = f"任务：{task.title}（{when}）"
        items.append(("task", task.id, due, title, task.contact_id))
    return items


async def _collect_repayment_items(db: AsyncSession, user: User, today: date) -> list[tuple]:
    """还款源：未结清且设了应收/应还日、进窗口的（direction 收为应收，出为应还）。"""
    from app.modules.funds import service as funds_service

    flows = await funds_service.list_fund_flows(
        db, user, search=None, direction=None, category=None, status="pending", contact_id=None
    )
    items = []
    for flow in flows:
        if flow.due_at is None:
            continue
        due = flow.due_at
        if not _in_window(due, today):
            continue
        days_left = (due - today).days
        kind = "应收" if flow.direction == "in" else "应还"
        title = f"{kind}{flow.amount:g} 元（{_when_label(days_left)}）"
        items.append(("repayment", flow.id, due, title, flow.contact_id))
    return items


async def _collect_date_items(db: AsyncSession, user: User, today: date) -> list[tuple]:
    """重要日期源：复用 contacts 的提醒口径（农历/滚动明年/提前量窗口）。"""
    from app.modules.contacts import service as contacts_service

    items = []
    date_kinds = {"birthday": "生日", "anniversary": "纪念日", "memorial": "忌日"}
    for reminder in await contacts_service.upcoming_date_reminders(db, user, today=today):
        when = "就是今天" if reminder.days_left == 0 else f"还有 {reminder.days_left} 天"
        kind = date_kinds.get(reminder.date_type, "重要日期")
        title = f"{reminder.contact_name}的{kind}{reminder.lunar_label or ''}（{when}）"
        items.append(("date", reminder.date_id, reminder.next_date, title, reminder.contact_id))
    return items


async def scan_user(db: AsyncSession, user: User) -> ScanStats:
    """对单个用户做一次三源扫描与幂等重建；返回统计。

    流程：三源装载 → 按来源逐个 upsert（未读刷新快照、已读不复活）
    → 每来源清理"源头消失"的未读 → flush 由调用方提交。
    """
    today = date.today()
    stats = ScanStats()

    collectors = (
        ("date", _collect_date_items),
        ("task", _collect_task_items),
        ("repayment", _collect_repayment_items),
    )
    for source, collector in collectors:
        alive_keys: set[tuple[int, date]] = set()
        for _source, ref_id, due, title, contact_id in await collector(db, user, today):
            created = await reminder_repo.upsert(
                db,
                user_id=user.id,
                family_id=user.family_id,
                source=source,
                ref_id=ref_id,
                due_date=due,
                days_left=(due - today).days,
                title=title,
                contact_id=contact_id,
            )
            if created:
                stats.created += 1
            else:
                stats.refreshed += 1
            alive_keys.add((ref_id, due))
        stats.removed += await reminder_repo.delete_unread_not_in(
            db, user.id, source, alive_keys
        )
        stats.sources[source] = len(alive_keys)
    await db.flush()
    return stats


async def list_reminders(db: AsyncSession, user: User, *, unread_only: bool):
    """某用户的提醒列表（未读在前）。"""
    return await reminder_repo.list_reminders(db, user.id, unread_only=unread_only)


async def unread_count(db: AsyncSession, user: User) -> int:
    """未读数（铃铛徽标）。"""
    return await reminder_repo.unread_count(db, user.id)


async def mark_read(db: AsyncSession, user: User, reminder_id: int) -> None:
    """标记单条已读；非本人的提醒按不存在处理（防越权探测）。"""
    reminder = await reminder_repo.get_user_reminder(db, user.id, reminder_id)
    if reminder is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("提醒不存在")
    if reminder.read_at is None:
        reminder.read_at = datetime.now(UTC)
        await db.flush()


async def mark_all_read(db: AsyncSession, user: User) -> int:
    """全部已读；返回条数。"""
    return await reminder_repo.mark_all_read(db, user.id)
