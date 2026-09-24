"""graph 模块 ORM 模型：RelationshipType / Relationship。

表结构不变（自 contacts 模块迁入，2026-09-21 模块治理 D12）：迁移无需变更，仅代码归属调整。
"""

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import OwnershipMixin, TimestampMixin

# 关系类型分组（借鉴 Monica 的类型字典思想，内容中文原生）
RELATION_GROUP_VALUES = ("family", "friend", "work", "romance", "other")


class RelationshipType(Base, TimestampMixin):
    """关系类型字典：正向/反向标签（丈夫↔妻子），NULL 反向=对称关系（同事）。"""

    __tablename__ = "relationship_types"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(
        Enum(*RELATION_GROUP_VALUES, name="relation_group_enum"), comment="分组"
    )
    name: Mapped[str] = mapped_column(String(50), comment="正向标签")
    reverse_name: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="反向标签")
    sort_order: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", comment="展示排序"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
        comment="系统结构化类型（可参与称谓推导，D15）",
    )
    kind: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="结构类别：parent/spouse/sibling（自定义类型为 NULL）"
    )


class Relationship(Base, TimestampMixin, OwnershipMixin):
    """关系边：图的边。可见性不落库，由两端联系人可见性取交集（D7 细化）。"""

    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("from_contact_id", "to_contact_id", "type_id", name="uq_relation_edge"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), index=True, comment="主体联系人"
    )
    to_contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), index=True, comment="客体联系人"
    )
    type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("relationship_types.id"), comment="关系类型"
    )
    from_role: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="from 是 to 的角色（father/husband/elder_brother…，D15）"
    )
    to_role: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="to 是 from 的角色"
    )
    status: Mapped[str] = mapped_column(
        String(10), default="active", server_default="active", comment="active / former"
    )
    note: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="补充说明")
