"""funds 模块 ORM 模型：FundFlow（资金往来流水）。

status 语义：NULL=不涉及结清（礼金/普通收支）；due_at 存在时为 pending/settled，
是主页"还款提醒"待办的数据源（due_at 未结清）。
"""

from datetime import date

from sqlalchemy import BigInteger, Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import OwnershipMixin, TimestampMixin

FUND_DIRECTION_VALUES = ("out", "in")
FUND_CATEGORY_VALUES = ("loan", "repayment", "gift_money", "other")
FUND_STATUS_VALUES = ("pending", "settled")


class FundFlow(Base, TimestampMixin, OwnershipMixin):
    """资金往来：借出/借入/礼金/代付等与联系人之间的资金流水。"""

    __tablename__ = "fund_flows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), nullable=True, index=True, comment="对象联系人"
    )
    direction: Mapped[str] = mapped_column(
        Enum(*FUND_DIRECTION_VALUES, name="fund_direction_enum"),
        comment="out 流出（借出/支出） / in 流入（借入/收到）",
    )
    category: Mapped[str] = mapped_column(
        Enum(*FUND_CATEGORY_VALUES, name="fund_category_enum"),
        comment="loan 借款 / repayment 还款 / gift_money 礼金 / other 其他",
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), comment="金额")
    currency: Mapped[str] = mapped_column(
        String(8), default="CNY", server_default="CNY", comment="币种"
    )
    occurred_at: Mapped[date] = mapped_column(Date, comment="发生日")
    due_at: Mapped[date | None] = mapped_column(Date, nullable=True, comment="应收/应还日")
    status: Mapped[str | None] = mapped_column(
        Enum(*FUND_STATUS_VALUES, name="fund_status_enum"),
        nullable=True,
        default=None,
        server_default=None,
        comment="pending 未结清 / settled 已结清 / NULL 不涉及",
    )
    settled_at: Mapped[date | None] = mapped_column(Date, nullable=True, comment="结清日")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="说明（Markdown）")
