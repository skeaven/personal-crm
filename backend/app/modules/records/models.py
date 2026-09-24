"""records 模块 ORM 模型：Note / Task / Activity / ActivityParticipant。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import ActivationMixin, OwnershipMixin, TimestampMixin

TASK_STATUS_VALUES = ("todo", "done", "cancelled")


class Note(Base, TimestampMixin, OwnershipMixin, ActivationMixin):
    """备注：可挂在联系人下，也可作为家庭自由笔记。"""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text, comment="正文")


class Task(Base, TimestampMixin, OwnershipMixin):
    """待办：AI 录入的高频目标之一（R3）。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), comment="标题")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="详情")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(*TASK_STATUS_VALUES, name="task_status_enum"),
        default="todo",
        server_default="todo",
        comment="todo / done / cancelled",
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Activity(Base, TimestampMixin, OwnershipMixin, ActivationMixin):
    """活动/聚会记录：一次活动对多名参与者（一对多），经 ActivityParticipant 关联。

    contact_id 已弃用（2026-09-21 用户定稿），迁移把存量单联系人转入参与者表。
    """

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), comment="活动标题")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="地点")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="记录详情（Markdown）")


class ActivityParticipant(Base):
    """活动参与者关联：活动↔联系人 一对多的桥表（唯一约束防重复挂人）。

    不带 D7 三件套：参与者行的可见性完全跟随活动本身，不单独判权。
    """

    __tablename__ = "activity_participants"
    __table_args__ = (
        UniqueConstraint("activity_id", "contact_id", name="uq_activity_participant"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("activities.id", ondelete="CASCADE"),
        index=True,
        comment="所属活动",
    )
    contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), index=True, comment="参与者联系人"
    )
