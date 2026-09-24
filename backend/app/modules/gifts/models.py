"""gifts 模块 ORM 模型：Gift / WishlistItem（人情礼物域的两个状态面）。

两个表共用 D7 三件套；删除均为硬删（流水型记录，无历史引用保护需求）。
"""

from datetime import date

from sqlalchemy import BigInteger, Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import OwnershipMixin, TimestampMixin

GIFT_DIRECTION_VALUES = ("given", "received")
WISHLIST_STATUS_VALUES = ("open", "purchased", "given")


class Gift(Base, TimestampMixin, OwnershipMixin):
    """礼物往来：已送出/已收到的人情记录（金额、场合可选，说明 Markdown）。"""

    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), nullable=True, index=True, comment="对象联系人"
    )
    direction: Mapped[str] = mapped_column(
        Enum(*GIFT_DIRECTION_VALUES, name="gift_direction_enum"),
        comment="given 送出 / received 收到",
    )
    title: Mapped[str] = mapped_column(String(200), comment="礼物名称")
    occasion: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="场合（生日/婚礼/探病…自由文本）"
    )
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True, comment="金额")
    currency: Mapped[str] = mapped_column(
        String(8), default="CNY", server_default="CNY", comment="币种"
    )
    given_at: Mapped[date | None] = mapped_column(Date, nullable=True, comment="送出/收到日期")
    link: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="购买/参考链接"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="说明（Markdown）")


class WishlistItem(Base, TimestampMixin, OwnershipMixin):
    """愿望清单：还没送出的礼物计划，状态机 想送→已购买→已送出。

    送出后经 convert 生成 Gift 并以 converted_gift_id 回链，两个状态面互不覆盖。
    """

    __tablename__ = "wishlist_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), nullable=True, index=True, comment="为谁准备"
    )
    title: Mapped[str] = mapped_column(String(200), comment="想送的礼物")
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True, comment="预算/价格")
    currency: Mapped[str] = mapped_column(
        String(8), default="CNY", server_default="CNY", comment="币种"
    )
    link: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="购买链接")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="说明（Markdown）")
    status: Mapped[str] = mapped_column(
        Enum(*WISHLIST_STATUS_VALUES, name="wishlist_status_enum"),
        default="open",
        server_default="open",
        comment="open 想送 / purchased 已购买 / given 已送出",
    )
    target_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="打算送出的日期（如对方生日）"
    )
    converted_gift_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("gifts.id"), nullable=True, comment="转成礼物记录后的回链"
    )
