"""联系人写工具执行器：确认队列的落库端。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.contacts import service as contacts_service
from app.modules.contacts.schemas import ContactCreate, ContactUpdate

# D23 之前的 create_contact payload 用姓/名两键；姓名已并为 name，旧键会被 pydantic
# 静默忽略（extra 默认 ignore），放过去就会丢掉姓名建出一条无名联系人，故显式拦下。
_STALE_CONTACT_KEYS = ("last_name", "first_name", "display_name_override")


async def create_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """执行建联系人：走 contacts 正常创建（自带同名检测 D7）；被拦截就把提醒
    写进 result——绝不用 confirm_duplicate=True 绕过，同名合并是人该做的决定。

    payload 是持久化 JSON，可能来自更早的契约（D23 姓名合并前），先拦旧键。
    """
    stale = [key for key in _STALE_CONTACT_KEYS if key in payload]
    if stale:
        return {
            "ok": False,
            "error": (
                f"该提议生成于姓名合并之前，字段 {'/'.join(stale)} 已失效，"
                "请拒绝后重新发起"
            ),
        }

    response = await contacts_service.create_contact(db, user, ContactCreate(**payload))
    if not response.created:
        names = "、".join(w.display_name for w in response.duplicate_warnings) or "同名联系人"
        return {
            "ok": False,
            "error": f"同名提醒：{names} 已存在，未创建。可拒绝此提议，或去名册处理",
        }
    assert response.contact is not None
    return {
        "ok": True,
        "message": f"联系人已创建（id={response.contact.id}）：{response.contact.display_name}",
    }


async def update_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """改联系人：走 contacts service 的 PATCH 语义（只改提交的字段）。"""
    data = ContactUpdate(**{key: value for key, value in payload.items() if key != "contact_id"})
    contact = await contacts_service.update_contact(db, user, payload["contact_id"], data)
    return {"ok": True, "message": f"已更新 {contact.display_name}（id={contact.id}）"}


async def delete_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """归档联系人（软删，仅所有者）：与 HTTP 的 DELETE 端点同一个 service 函数。"""
    await contacts_service.archive_contact(db, user, payload["contact_id"])
    return {"ok": True, "message": "已归档该联系人"}


async def promote_contact(db: AsyncSession, user: User, payload: dict) -> dict:
    """边缘联系人升级为直接联系人：升级保留全部数据（与其他入口同一个函数）。"""
    contact = await contacts_service.promote_contact(db, user, payload["contact_id"])
    return {"ok": True, "message": f"{contact.display_name} 已升级为直接联系人"}
