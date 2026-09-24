"""ai 模块向量化内容装载器：五源（联系人/活动/礼物/资金/备注）→ 统一条目。

条目形状：(entity_type, entity_id, content, owner_user_id, family_id, visibility)。
装载按当前用户可读范围（D7）；可见性快照自源数据；文本模板是内容质量的唯一控制点。
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.contacts.models import Contact
from app.modules.funds.models import FundFlow
from app.modules.gifts.models import Gift
from app.modules.records.models import Activity, Note
from app.services.permission import readable_condition

_FUND_CATEGORY = {"loan": "借款", "repayment": "还款", "gift_money": "礼金", "other": "资金"}


class SourceEntry:
    """待向量化条目。"""

    __slots__ = ("entity_type", "entity_id", "content", "owner_user_id", "family_id", "visibility")

    def __init__(self, entity_type: str, entity_id: int, content: str,
                 owner_user_id: int, family_id: int, visibility: str) -> None:
        """固化五元组。"""
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.content = content
        self.owner_user_id = owner_user_id
        self.family_id = family_id
        self.visibility = visibility

    def key(self) -> tuple[str, int]:
        """元数据关联键（与 embeddings 表唯一约束一致）。"""
        return (self.entity_type, self.entity_id)


def _contact_text(contact: Contact) -> str:
    """联系人内容模板。"""
    parts = [f"联系人：{contact.display_name}"]
    if contact.nickname and contact.nickname != contact.display_name:
        parts.append(f"称呼「{contact.nickname}」")
    if contact.organization:
        parts.append(f"单位 {contact.organization}")
    if contact.location:
        parts.append(f"所在地 {contact.location}")
    if contact.phone:
        parts.append(f"电话 {contact.phone}")
    if contact.wechat:
        parts.append(f"微信 {contact.wechat}")
    if contact.school_name:
        parts.append(f"毕业院校 {contact.school_name}")
    if contact.hobbies:
        parts.append(f"兴趣爱好 {contact.hobbies}")
    if contact.current_address:
        parts.append(f"现居 {contact.current_address}")
    if contact.bio:
        parts.append(contact.bio)
    return "；".join(parts)


async def collect_sources(db: AsyncSession, user: User) -> list[SourceEntry]:
    """装载当前用户可读的全部可向量化条目（五源；随管线扩充）。"""
    entries: list[SourceEntry] = []

    contacts = (
        await db.execute(
            select(Contact).where(
                Contact.status == "active", readable_condition(Contact, user)
            )
        )
    ).scalars().all()
    for c in contacts:
        entries.append(SourceEntry("contact", c.id, _contact_text(c),
                                   c.owner_user_id, c.family_id, c.visibility))

    activities = (
        await db.execute(
            select(Activity).where(
                Activity.is_active.is_(True),
                Activity.occurred_at.is_not(None),
                readable_condition(Activity, user),
            )
        )
    ).scalars().all()
    for a in activities:
        day = a.occurred_at.astimezone().date().isoformat() if a.occurred_at else ""
        text = f"活动「{a.title}」于 {day}" + (f"，在 {a.location}" if a.location else "")
        if a.detail:
            text += f"：{a.detail}"
        entries.append(SourceEntry("activity", a.id, text,
                                   a.owner_user_id, a.family_id, a.visibility))

    gifts = (
        await db.execute(select(Gift).where(readable_condition(Gift, user)))
    ).scalars().all()
    for g in gifts:
        direction = "送出" if g.direction == "given" else "收到"
        text = f"礼物（{direction}）「{g.title}」"
        if g.occasion:
            text += f"，场合 {g.occasion}"
        if g.amount is not None:
            text += f"，{g.amount} 元"
        if g.description:
            text += f"：{g.description}"
        entries.append(SourceEntry("gift", g.id, text,
                                   g.owner_user_id, g.family_id, g.visibility))

    funds = (
        await db.execute(select(FundFlow).where(readable_condition(FundFlow, user)))
    ).scalars().all()
    for f in funds:
        direction = "流出" if f.direction == "out" else "流入"
        text = f"资金（{_FUND_CATEGORY.get(f.category, '资金')}，{direction}）{f.amount} 元"
        text += f"，发生日 {f.occurred_at.isoformat()}"
        if f.description:
            text += f"：{f.description}"
        entries.append(SourceEntry("fund", f.id, text,
                                   f.owner_user_id, f.family_id, f.visibility))

    notes = (
        await db.execute(select(Note).where(readable_condition(Note, user)))
    ).scalars().all()
    for n in notes:
        entries.append(SourceEntry("note", n.id, f"备注：{n.content}",
                                   n.owner_user_id, n.family_id, n.visibility))

    return entries
