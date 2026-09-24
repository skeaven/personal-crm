"""contacts 模块 ORM 模型：Contact / ImportantDate（关系边已迁往 graph 模块）。"""

from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Double,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import ActivationMixin, OwnershipMixin, TimestampMixin

# 联系人层级（双层模型）：direct 走完整管理；edge 是挂靠在 direct 下的最小信息叶子
TIER_DIRECT = "direct"
TIER_EDGE = "edge"
TIER_VALUES = (TIER_DIRECT, TIER_EDGE)

GENDER_VALUES = ("male", "female", "other", "unknown")

DATE_TYPE_VALUES = ("birthday", "anniversary", "memorial", "other")
CALENDAR_VALUES = ("solar", "lunar")


class Contact(Base, TimestampMixin, OwnershipMixin, ActivationMixin):
    """联系人：direct/edge 同表分层，升级只改 tier，数据无损（R6）。"""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tier: Mapped[str] = mapped_column(
        Enum(*TIER_VALUES, name="contact_tier_enum"),
        default=TIER_DIRECT,
        server_default=TIER_DIRECT,
        comment="direct 直接联系人 / edge 边缘联系人",
    )
    last_name: Mapped[str] = mapped_column(String(50), default="", server_default="", comment="姓")
    first_name: Mapped[str] = mapped_column(
        String(50), default="", server_default="", comment="名"
    )
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="昵称/称呼")
    display_name_override: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="手动指定展示名，优先级最高"
    )
    gender: Mapped[str] = mapped_column(
        Enum(*GENDER_VALUES, name="gender_enum"),
        default="unknown",
        server_default="unknown",
        comment="性别",
    )
    organization: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="单位")
    # 联系方式（2026-09-23 资料扩充）
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="电话")
    qq: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="QQ 号")
    wechat: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="微信号")
    email: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="邮箱")
    # 地址与个人背景
    current_address: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="现居地"
    )
    family_address: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="家庭地址"
    )
    hobbies: Mapped[str | None] = mapped_column(String(300), nullable=True, comment="兴趣爱好")
    school_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="毕业院校")
    location: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="所在地文本，保存时经 geo 解析坐标（D14）"
    )
    location_lng: Mapped[float | None] = mapped_column(
        Double(), nullable=True, comment="经度缓存（location 变更才重算）"
    )
    location_lat: Mapped[float | None] = mapped_column(Double(), nullable=True, comment="纬度缓存")
    location_source: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="坐标来源：amap/static/none（NULL=未填位置）"
    )
    location_province: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="所属省级名称（地图 choropleth 聚合维度）"
    )
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, comment="一句话简介")
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="头像路径")
    status: Mapped[str] = mapped_column(
        Enum("active", "archived", name="contact_status_enum"),
        default="active",
        server_default="active",
        comment="active 在册 / archived 归档",
    )

    important_dates: Mapped[list["ImportantDate"]] = relationship(back_populates="contact")

    @property
    def display_name(self) -> str:
        """展示名规则（唯一实现点，DATA_MODEL.md 第 2 节）：覆盖名 > 昵称 > 姓+名。"""
        if self.display_name_override and self.display_name_override.strip():
            return self.display_name_override.strip()
        if self.nickname and self.nickname.strip():
            return self.nickname.strip()
        full_name = f"{self.last_name}{self.first_name}".strip()
        return full_name or self.first_name.strip() or "（未命名）"


class ImportantDate(Base, TimestampMixin, OwnershipMixin):
    """重要日期：公历/农历双历法原生支持（R1/D8），农历字段在 lunar 历法下必填。"""

    __tablename__ = "important_dates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contacts.id"), index=True, comment="所属联系人"
    )
    type: Mapped[str] = mapped_column(
        Enum(*DATE_TYPE_VALUES, name="date_type_enum"), comment="日期类型"
    )
    title: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="自定义名称")
    calendar: Mapped[str] = mapped_column(
        Enum(*CALENDAR_VALUES, name="calendar_enum"), comment="历法：solar 公历 / lunar 农历"
    )
    date_solar: Mapped[date | None] = mapped_column(Date, nullable=True, comment="公历日期")
    lunar_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, comment="农历月")
    lunar_day: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, comment="农历日")
    lunar_is_leap: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="是否闰月"
    )
    yearly: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="是否每年重复"
    )
    reminder_lead_days: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", comment="提前提醒天数列表，如 [7,1]"
    )

    contact: Mapped[Contact] = relationship(back_populates="important_dates")
