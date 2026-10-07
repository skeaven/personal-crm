"""执行器共用助手：payload 字段解析（各模块执行器共享，避免各写一份）。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError
from app.modules.ai.registry import resolve_contact_name
from app.modules.auth.models import User


async def resolve_contact_id(db: AsyncSession, user: User, payload: dict) -> int | None:
    """payload.contact_name → 联系人 id；未提供返回 None，找不到即业务错误。

    执行器拿到的 id 用于落库，所以找不到必须报错而不是静默传 None——
    静默会让"记活动时关联人写错"这种错误无声发生。
    """
    name = payload.get("contact_name")
    if not name:
        return None
    resolved = await resolve_contact_name(db, user, name)
    if resolved is None:
        raise BusinessError(f"没有找到联系人「{name}」，请先在名册中记录")
    return resolved
