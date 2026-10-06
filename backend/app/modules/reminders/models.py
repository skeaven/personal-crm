"""reminders 模块 ORM 模型：Reminder（应用内提醒，D22）。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin

# 提醒来源（口径与 dashboard 待办四桶同源，但活动不进提醒——临近活动主页已可见）
REMINDER_SOURCE_VALUES = ("date", "task", "repayment")
# 通知渠道：本期只落应用内；email 留 provider 位
REMINDER_CHANNEL_VALUES = ("inapp", "email")


class Reminder(Base, TimestampMixin):
    """应用内提醒：由扫描器从三源幂等重建，用户可逐条/全部标记已读。

    幂等键 (user_id, source, ref_id, due_date)：同一事项同一到期日只有一条；
    read_at 非空表示已读，同键已读不复活；源头消失时未读由清理逻辑删除。
    title/days_left 是生成时点的快照（重建时刷新未读行）。
    """

    __tablename__ = "reminders"
    __table_args__ = (
        # 幂等唯一键在迁移里以 uq_reminder_once 命名创建；模型侧声明约束保证 create_all 一致
        None,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, comment="提醒归属用户"
    )
    family_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("families.id"), index=True, comment="冗余家庭 ID"
    )
    source: Mapped[str] = mapped_column(String(20), comment="来源：date/task/repayment")
    ref_id: Mapped[int] = mapped_column(BigInteger, comment="来源业务 id")
    due_date: Mapped[date] = mapped_column(Date, comment="到期日（幂等键组成部分）")
    days_left: Mapped[int] = mapped_column(Integer, comment="生成时点的剩余天数快照")
    title: Mapped[str] = mapped_column(String(200), comment="提醒文案快照")
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), nullable=True, comment="关联联系人（跳转用）"
    )
    channel: Mapped[str] = mapped_column(
        String(10), default="inapp", server_default="inapp", comment="通知渠道"
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="已读时间；NULL=未读"
    )
