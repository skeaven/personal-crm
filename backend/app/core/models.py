"""ORM 公共混入：时间戳、D7 所有权三件套、归档开关。

放在 core 层以避免循环导入（业务模块 → core 单向依赖）；
所有业务表通过混入获得统一字段，权限判定因此可以写成一处（app/services/permission.py）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

# 可见性两档（D7）：private 仅所有者可见；family 家庭成员只读可见
VISIBILITY_VALUES = ("private", "family")


class TimestampMixin:
    """created_at / updated_at 由数据库自动维护。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


class OwnershipMixin:
    """D7 权限三件套：所有者（唯一可写）+ 家庭（查询范围）+ 可见性（共享读取）。"""

    owner_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, comment="所有者（创建者），唯一可写"
    )
    family_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("families.id"),
        index=True,
        comment="所属家庭，服务层保证与所有者一致",
    )
    visibility: Mapped[str] = mapped_column(
        Enum(*VISIBILITY_VALUES, name="visibility_enum"),
        default="family",
        server_default="family",
        comment="可见性：private 私密 / family 家庭可见只读",
    )


class ActivationMixin:
    """归档开关：用 status=archived 代替物理删除，保护历史引用（如关系边）。"""

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="false 表示已归档"
    )
