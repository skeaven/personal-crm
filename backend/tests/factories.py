"""测试造数工厂：直接经 ORM 创建家庭/用户/联系人/日期/生活记录，绕过 API 层。"""

from datetime import date

from httpx import AsyncClient

from app.core.db import get_session_factory
from app.core.security import hash_password
from app.modules.auth.models import Family, User
from app.modules.contacts.models import Contact, ImportantDate
from app.modules.funds.models import FundFlow
from app.modules.gifts.models import Gift, WishlistItem
from app.modules.records.models import Activity, ActivityParticipant, Task


async def create_family_user(
    family_name: str = "测试家庭",
    username: str = "demo",
    display_name: str = "阿澄",
    password: str = "demo12345",
    family_id: int | None = None,
) -> tuple[User, str]:
    """创建（或复用家庭后）一个用户，返回 (用户, 明文密码)。

    传入 family_id 时加入既有家庭（模拟同一家庭的第二个成员）。
    """
    factory = get_session_factory()
    async with factory() as session:
        if family_id is None:
            family = Family(name=family_name)
            session.add(family)
            await session.flush()
            family_id = family.id
        user = User(
            family_id=family_id,
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, password


async def create_contact_for(user: User, **fields) -> Contact:
    """为指定用户创建一条联系人记录，返回带 id 的 ORM 对象。"""
    factory = get_session_factory()
    async with factory() as session:
        contact = Contact(
            owner_user_id=user.id,
            family_id=user.family_id,
            **fields,
        )
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return contact


async def create_date_for(user: User, contact_id: int, **fields) -> ImportantDate:
    """为指定用户在某联系人下创建一条重要日期记录。"""
    _coerce_date_fields(fields, ("date_solar",))
    factory = get_session_factory()
    async with factory() as session:
        record = ImportantDate(
            owner_user_id=user.id,
            family_id=user.family_id,
            contact_id=contact_id,
            **fields,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


async def create_activity_for(user: User, *, participant_contact_ids=(), **fields) -> Activity:
    """创建活动并挂上参与者（contact_id 列表），返回带 id 的活动 ORM 对象。"""
    factory = get_session_factory()
    async with factory() as session:
        activity = Activity(owner_user_id=user.id, family_id=user.family_id, **fields)
        session.add(activity)
        await session.flush()
        for contact_id in participant_contact_ids:
            session.add(
                ActivityParticipant(activity_id=activity.id, contact_id=contact_id)
            )
        await session.commit()
        await session.refresh(activity)
        return activity


async def create_task_for(user: User, **fields) -> Task:
    """创建一条待办任务，返回带 id 的 ORM 对象。"""
    factory = get_session_factory()
    async with factory() as session:
        task = Task(owner_user_id=user.id, family_id=user.family_id, **fields)
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


def _coerce_date_fields(fields: dict, keys: tuple[str, ...]) -> dict:
    """把 ISO 日期字符串统一转成 date 对象（ORM 不做字符串到日期的隐式转换）。"""
    for key in keys:
        if isinstance(fields.get(key), str):
            fields[key] = date.fromisoformat(fields[key])
    return fields


async def create_gift_for(user: User, **fields) -> Gift:
    """创建一条礼物往来记录，返回带 id 的 ORM 对象。"""
    _coerce_date_fields(fields, ("given_at",))
    factory = get_session_factory()
    async with factory() as session:
        gift = Gift(owner_user_id=user.id, family_id=user.family_id, **fields)
        session.add(gift)
        await session.commit()
        await session.refresh(gift)
        return gift


async def create_wishlist_for(user: User, **fields) -> WishlistItem:
    """创建一条愿望清单项，返回带 id 的 ORM 对象。"""
    _coerce_date_fields(fields, ("target_date",))
    factory = get_session_factory()
    async with factory() as session:
        item = WishlistItem(owner_user_id=user.id, family_id=user.family_id, **fields)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def create_fund_for(user: User, **fields) -> FundFlow:
    """创建一条资金往来记录，返回带 id 的 ORM 对象。"""
    _coerce_date_fields(fields, ("occurred_at", "due_at", "settled_at"))
    factory = get_session_factory()
    async with factory() as session:
        fund = FundFlow(owner_user_id=user.id, family_id=user.family_id, **fields)
        session.add(fund)
        await session.commit()
        await session.refresh(fund)
        return fund


async def login_as(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    """经 API 登录，返回 Authorization 请求头。"""
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, f"登录失败: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
