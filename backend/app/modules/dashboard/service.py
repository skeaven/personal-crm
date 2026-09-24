"""dashboard 模块服务层：待办与时间线的聚合编排（纯消费，不拥有业务表）。

衔接点设计（2026-09-21 用户定稿）：待办是全系统时间义务的统一视图，
五来源 = 手工任务 / 心愿送出日 / 还款应还日 / 未来活动 / 重要日期（生日）。
详情页时间线（2026-09-21）：三源（礼物/资金/活动）归并为倒序游标分页流。
各来源数据仍归各自模块管，这里只读聚合；权限随各模块可读查询天然生效。
"""

from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.contacts import repository as contacts_repo
from app.modules.contacts import service as contacts_service
from app.modules.dashboard.schemas import TimelineItemOut, TimelineOut, TodoItemOut
from app.modules.funds import service as funds_service
from app.modules.gifts import service as gifts_service
from app.modules.records import service as records_service

# 还款类目的中文标题映射（fund_flows 无标题字段，按类别生成）
_REPAYMENT_TITLES = {
    "loan": "借款到期",
    "repayment": "应收还款",
    "gift_money": "礼金记录",
    "other": "资金事项",
}

_FUND_CATEGORY_LABELS = {
    "loan": "借款",
    "repayment": "还款",
    "gift_money": "礼金",
    "other": "其他",
}

# 纯日期源在归并排序中的日内偏移（小时）：固定错开使跨源时刻唯一、游标不丢数据
_GIFT_HOUR = 8
_FUND_HOUR = 12


async def build_todo_board(
    db: AsyncSession, user: User, bucket: str, today: date | None = None
) -> list[TodoItemOut]:
    """组装待办看板：采集五来源 → 归桶 → 按 deadline 排序（近的在前）。

    bucket 取 todo/overdue/done/all；today 可注入（测试口径），默认当天。
    """
    the_day = today or date.today()
    now = datetime.now(UTC)

    open_items, done_items = await _collect_all_sources(db, user, the_day, now)

    if bucket == "todo":
        result = [item for item in open_items if item.bucket == "todo"]
    elif bucket == "overdue":
        result = [item for item in open_items if item.bucket == "overdue"]
    elif bucket == "done":
        result = done_items
    else:
        result = open_items + done_items

    return sorted(
        result,
        key=lambda item: (item.due_date is None, item.due_date or date.max, item.ref_id),
    )


async def _collect_all_sources(
    db: AsyncSession, user: User, the_day: date, now: datetime
) -> tuple[list[TodoItemOut], list[TodoItemOut]]:
    """采集五来源并划分 (未完成, 已完成) 两个列表；来源间互不依赖，顺序聚合。"""
    open_items: list[TodoItemOut] = []
    done_items: list[TodoItemOut] = []

    open_items.extend(await _collect_tasks(db, user, the_day, now, status="todo"))
    done_items.extend(await _collect_tasks(db, user, the_day, now, status="done"))

    wishes_todo, wishes_done = await _collect_wishes(db, user, the_day)
    open_items.extend(wishes_todo)
    done_items.extend(wishes_done)

    repay_todo, repay_done = await _collect_repayments(db, user, the_day)
    open_items.extend(repay_todo)
    done_items.extend(repay_done)

    open_items.extend(await _collect_activities(db, user, now, the_day))
    open_items.extend(await _collect_birthdays(db, user, the_day))

    return open_items, done_items


async def _collect_tasks(
    db: AsyncSession, user: User, the_day: date, now: datetime, *, status: str
) -> list[TodoItemOut]:
    """采集手工任务（agent/MCP 创建的任务同源）：todo 按截止日分待办/过期，done 直接完成。"""
    tasks = await records_service.list_tasks(db, user, status=status)
    contact_names = await contacts_service.get_display_name_map(
        db, user, [task.contact_id for task in tasks if task.contact_id]
    )

    items: list[TodoItemOut] = []
    for task in tasks:
        # due_at 是 UTC 时刻，按用户本地时区取日期，避免跨时区差一天的口径漂移
        due_date = task.due_at.astimezone().date() if task.due_at else None
        days_left = (due_date - the_day).days if due_date else None
        if status == "done":
            bucket = "done"
        else:
            bucket = "overdue" if due_date and days_left < 0 else "todo"
        items.append(
            TodoItemOut(
                source="task",
                ref_id=task.id,
                title=task.title,
                contact_id=task.contact_id,
                contact_name=contact_names.get(task.contact_id) if task.contact_id else None,
                due_date=due_date,
                days_left=days_left,
                bucket=bucket,
            )
        )
    return items


async def _collect_wishes(
    db: AsyncSession, user: User, the_day: date
) -> tuple[list[TodoItemOut], list[TodoItemOut]]:
    """采集心愿送出计划：定了送出日的 想送/已购买 进待办（过期即"过了日子没送"），已送出进完成。"""
    open_wishes = await gifts_service.list_upcoming_wishes(
        db, user, statuses=("open", "purchased"), with_target_date=True
    )
    done_wishes = await gifts_service.list_upcoming_wishes(db, user, statuses=("given",))

    contact_ids = [wish.contact_id for wish in open_wishes + done_wishes if wish.contact_id]
    contact_names = await contacts_service.get_display_name_map(db, user, contact_ids)

    def _open_bucket(wish) -> str:
        """已过送出日仍未送出 → 过期桶，否则待办。"""
        return "overdue" if (wish.target_date - the_day).days < 0 else "todo"

    open_items = [
        _wish_item(wish, contact_names, the_day, bucket=_open_bucket(wish))
        for wish in open_wishes
    ]
    done_items = [
        _wish_item(wish, contact_names, the_day, bucket="done") for wish in done_wishes
    ]
    return open_items, done_items


def _wish_item(
    wish, contact_names: dict[int, str], the_day: date, *, bucket: str
) -> TodoItemOut:
    """组装心愿待办项（目标日期为 due；标题即礼物名，联系人在 contact 字段）。

    已送出（done 桶）的愿望可能没填过目标日期，days_left/due_date 容许为空。
    """
    days_left = (wish.target_date - the_day).days if wish.target_date else None
    return TodoItemOut(
        source="wish",
        ref_id=wish.id,
        title=wish.title,
        contact_id=wish.contact_id,
        contact_name=contact_names.get(wish.contact_id) if wish.contact_id else None,
        due_date=wish.target_date,
        days_left=days_left,
        bucket=bucket,
    )


async def _collect_repayments(
    db: AsyncSession, user: User, the_day: date
) -> tuple[list[TodoItemOut], list[TodoItemOut]]:
    """采集资金义务：未结清且带应还日的流水进待办（过期=该收没收），已结清进完成。"""
    pending = await funds_service.list_fund_flows(
        db, user, search=None, direction=None, category=None, status="pending", contact_id=None
    )
    pending = [flow for flow in pending if flow.due_at is not None]
    settled = await funds_service.list_fund_flows(
        db, user, search=None, direction=None, category=None, status="settled", contact_id=None
    )

    contact_ids = [flow.contact_id for flow in pending + settled if flow.contact_id]
    contact_names = await contacts_service.get_display_name_map(db, user, contact_ids)

    def _item(flow, bucket: str) -> TodoItemOut:
        days_left = (flow.due_at - the_day).days
        return TodoItemOut(
            source="repayment",
            ref_id=flow.id,
            title=_REPAYMENT_TITLES.get(flow.category, "资金事项"),
            contact_id=flow.contact_id,
            contact_name=contact_names.get(flow.contact_id) if flow.contact_id else None,
            due_date=flow.due_at,
            days_left=days_left,
            bucket=bucket,
        )

    open_items = [
        _item(flow, "overdue" if (flow.due_at - the_day).days < 0 else "todo") for flow in pending
    ]
    done_items = [_item(flow, "done") for flow in settled]
    return open_items, done_items


async def _collect_activities(
    db: AsyncSession, user: User, now: datetime, the_day: date
) -> list[TodoItemOut]:
    """采集未来活动（即将到来的事）；已发生的活动是历史，不进任何待办桶。"""
    activities = await records_service.list_upcoming_activities(db, user, from_time=now)

    contact_ids: list[int] = []
    for activity in activities:
        contact_ids.extend(activity.participant_ids)
    contact_names = await contacts_service.get_display_name_map(db, user, contact_ids)

    items: list[TodoItemOut] = []
    for activity in activities:
        if activity.occurred_at is None:
            continue  # 未定时间的活动不产生待办（在活动页里可见）
        local_date = activity.occurred_at.astimezone().date()
        participants = [
            contact_names[pid] for pid in activity.participant_ids if pid in contact_names
        ]
        title = f"{activity.title}（{'、'.join(participants)}）" if participants else activity.title
        items.append(
            TodoItemOut(
                source="activity",
                ref_id=activity.id,
                title=title,
                due_date=local_date,
                days_left=(local_date - the_day).days,
                bucket="todo",
            )
        )
    return items


async def _collect_birthdays(db: AsyncSession, user: User, the_day: date) -> list[TodoItemOut]:
    """采集生日/纪念日提醒（contacts 域口径）：窗口内出现，过期自动滚明年，永不过期。"""
    reminders = await contacts_service.upcoming_date_reminders(db, user, today=the_day)

    return [
        TodoItemOut(
            source="birthday",
            ref_id=reminder.date_id,
            title=(
                f"{reminder.contact_name}{_DATE_TYPE_LABELS.get(reminder.date_type, '纪念日')}"
                if reminder.contact_name
                else (reminder.title or "纪念日")
            ),
            contact_id=reminder.contact_id,
            contact_name=reminder.contact_name,
            due_date=reminder.next_date,
            days_left=reminder.days_left,
            lunar_label=reminder.lunar_label,
            bucket="todo",
        )
        for reminder in reminders
    ]


_DATE_TYPE_LABELS = {
    "birthday": "的生日",
    "anniversary": "的纪念日",
    "memorial": "的忌日",
    "other": "的重要日期",
}


async def build_contact_timeline(
    db: AsyncSession, user: User, contact_id: int
) -> TimelineOut:
    """组装联系人时间线（详情页竖向流）：三源全量取数 → 内存归并 → 倒序一次返回。

    个人 CRM 数据量级小（2026-09-21 用户定稿）：不做服务端分页，一次性返回全部；
    "动态加载"的观感由前端切片渲染实现。联系人对用户不可见时按 404 处理。
    """
    contact = await contacts_repo.get_readable_contact(db, user, contact_id)
    if contact is None:
        raise NotFoundError("联系人不存在")

    gifts = await gifts_service.list_contact_gifts(db, user, contact_id=contact_id)
    funds = await funds_service.list_contact_fund_flows(db, user, contact_id=contact_id)
    activities = await records_service.list_contact_activities(db, user, contact_id=contact_id)

    items = [
        *_gift_items(gifts),
        *_fund_items(funds),
        *_activity_items(activities),
    ]
    items.sort(key=lambda item: item.occurred_at, reverse=True)
    return TimelineOut(contact_id=contact_id, items=items)


def _date_ts(day: date, hour: int) -> datetime:
    """纯日期 → 带日内偏移的排序时刻（UTC；展示层只取日期部分）。"""
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def _gift_items(gifts: list) -> list[TimelineItemOut]:
    """礼物 → 时间线条目：日期源偏移到 8 点，方向/金额/场合透传给前端渲染。"""
    items: list[TimelineItemOut] = []
    for gift in gifts:
        if gift.given_at is None:
            continue
        items.append(
            TimelineItemOut(
                source="gift",
                ref_id=gift.id,
                occurred_at=_date_ts(gift.given_at, _GIFT_HOUR),
                title=gift.title,
                summary=gift.description,
                amount=f"{gift.amount:.2f}" if gift.amount is not None else None,
                direction=gift.direction,
                extra_label=gift.occasion,
            )
        )
    return items


def _fund_items(funds: list) -> list[TimelineItemOut]:
    """资金流水 → 时间线条目：日期源偏移到 12 点，标题按类别生成。"""
    items: list[TimelineItemOut] = []
    for flow in funds:
        items.append(
            TimelineItemOut(
                source="fund",
                ref_id=flow.id,
                occurred_at=_date_ts(flow.occurred_at, _FUND_HOUR),
                title=_FUND_CATEGORY_LABELS.get(flow.category, "资金事项"),
                summary=flow.description,
                amount=f"{flow.amount:.2f}" if flow.amount is not None else None,
                direction=flow.direction,
                extra_label="已结清" if flow.status == "settled" else None,
            )
        )
    return items


def _activity_items(activities: list) -> list[TimelineItemOut]:
    """活动 → 时间线条目：用真实发生时刻；摘要拼接地点。"""
    items: list[TimelineItemOut] = []
    for activity in activities:
        if activity.occurred_at is None:
            continue
        items.append(
            TimelineItemOut(
                source="activity",
                ref_id=activity.id,
                occurred_at=activity.occurred_at,
                title=activity.title,
                summary=activity.location,
            )
        )
    return items
