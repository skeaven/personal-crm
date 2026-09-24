"""全局唯一权限判定点（D7/D11 红线）：所有读写都必须经过这里。"""

from sqlalchemy import ColumnElement, and_, or_

from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.models import OwnershipMixin


def readable_condition(model_cls: type[OwnershipMixin], user) -> ColumnElement[bool]:
    """构造"当前用户可读"的 SQL 条件：本人数据 或 家庭可见数据。"""
    return or_(
        model_cls.owner_user_id == user.id,
        and_(model_cls.visibility == "family", model_cls.family_id == user.family_id),
    )


def ensure_readable(user, record) -> None:
    """运行时读校验：不可读一律按 404 处理，不泄露私有数据的存在性。"""
    is_owner = record.owner_user_id == user.id
    is_family_readable = record.visibility == "family" and record.family_id == user.family_id
    if not (is_owner or is_family_readable):
        raise NotFoundError("资源不存在")


def ensure_can_write(user, record) -> None:
    """运行时写校验（D7）：只有所有者可写，家庭其他成员只读。"""
    if record.owner_user_id != user.id:
        raise PermissionDeniedError("只有创建者可以修改")
