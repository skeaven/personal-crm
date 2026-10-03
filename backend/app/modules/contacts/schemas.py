"""contacts 模块 Pydantic 模式：请求/响应契约（OpenAPI 生成前端类型的来源）。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.contacts.models import (
    CALENDAR_VALUES,
    DATE_TYPE_VALUES,
    GENDER_VALUES,
    TIER_DIRECT,
    TIER_VALUES,
)

VISIBILITY_INPUT_VALUES = ("private", "family")


class DuplicateWarning(BaseModel):
    """同名提醒项（D7 细化：创建环节的重复防线）。"""

    contact_id: int
    display_name: str
    owner_display_name: str
    tier: str


class ContactBase(BaseModel):
    """联系人公共字段。"""

    tier: str = TIER_DIRECT
    name: str = Field(default="", max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    gender: str = "unknown"
    organization: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    qq: str | None = Field(default=None, max_length=30)
    wechat: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=120)
    current_address: str | None = Field(default=None, max_length=200)
    family_address: str | None = Field(default=None, max_length=200)
    hobbies: str | None = Field(default=None, max_length=300)
    school_name: str | None = Field(default=None, max_length=100)
    location: str | None = Field(
        default=None, max_length=200, description="所在地文本，保存时服务端解析坐标"
    )
    bio: str | None = None
    visibility: str = "family"

    @model_validator(mode="after")
    def validate_enums(self) -> "ContactBase":
        """校验枚举取值，给前端可读的错误信息。"""
        if self.tier not in TIER_VALUES:
            raise ValueError(f"tier 必须是 {TIER_VALUES} 之一")
        if self.gender not in GENDER_VALUES:
            raise ValueError(f"gender 必须是 {GENDER_VALUES} 之一")
        if self.visibility not in VISIBILITY_INPUT_VALUES:
            raise ValueError("visibility 必须是 private 或 family")
        return self


class ContactCreate(ContactBase):
    """创建联系人：direct 至少要有姓名，edge 允许只有昵称（最小信息集）。"""

    confirm_duplicate: bool = Field(
        default=False, description="存在同名提醒时，前端需让用户确认后置 true 重发"
    )

    @model_validator(mode="after")
    def validate_name_presence(self) -> "ContactCreate":
        """至少能定位到一个人：姓名、昵称必有其一。"""
        if not any([self.name.strip(), (self.nickname or "").strip()]):
            raise ValueError("姓名、昵称至少填写一项")
        return self


class ContactUpdate(BaseModel):
    """更新联系人：全字段可选，仅提交的字段生效。"""

    tier: str | None = None
    name: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    gender: str | None = None
    organization: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    qq: str | None = Field(default=None, max_length=30)
    wechat: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=120)
    current_address: str | None = Field(default=None, max_length=200)
    family_address: str | None = Field(default=None, max_length=200)
    hobbies: str | None = Field(default=None, max_length=300)
    school_name: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    bio: str | None = None
    visibility: str | None = None


class ContactOut(BaseModel):
    """联系人输出：display_name 由服务端统一计算（DESIGN.md 展示名规则唯一实现点）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tier: str
    name: str
    nickname: str | None
    display_name: str
    gender: str
    organization: str | None
    phone: str | None
    qq: str | None
    wechat: str | None
    email: str | None
    current_address: str | None
    family_address: str | None
    hobbies: str | None
    school_name: str | None
    location: str | None
    location_lng: float | None
    location_lat: float | None
    location_source: str | None
    location_province: str | None
    bio: str | None
    visibility: str
    status: str
    owner_user_id: int
    owner_display_name: str
    created_at: datetime
    updated_at: datetime


class ImportantDateOut(BaseModel):
    """重要日期输出（详情页基础区块；农历的中文格式化由前端展示层处理）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str | None
    calendar: str
    date_solar: date | None
    lunar_month: int | None
    lunar_day: int | None
    lunar_is_leap: bool
    yearly: bool
    reminder_lead_days: list


class ContactDetailOut(ContactOut):
    """详情页输出：联系人全量 + 关联区块（详情页是系统核心枢纽，区块逐步增量）。

    约定：后续时间线 / 礼物往来 / 资金往来 / 愿望清单等功能落地时，
    在此模式上追加对应区块字段，前端详情页按区块渲染。
    """

    dates: list[ImportantDateOut] = []


class MapPointOut(BaseModel):
    """地图撒点：联系人坐标（仅有坐标缓存的可读联系人）。"""

    model_config = ConfigDict(from_attributes=True)

    contact_id: int
    display_name: str
    tier: str
    lng: float
    lat: float


class ProvinceCountOut(BaseModel):
    """省份计数（choropleth 着色维度）。"""

    name: str
    count: int


class MapPointsOut(BaseModel):
    """地图页数据：撒点 + 省份聚合。"""

    points: list[MapPointOut]
    provinces: list[ProvinceCountOut]


class ContactCreateResponse(BaseModel):
    """创建响应：created=false 表示被同名提醒拦截，前端展示警告后确认重发。"""

    created: bool
    contact: ContactOut | None = None
    duplicate_warnings: list[DuplicateWarning] = []


class ImportantDateCreate(BaseModel):
    """创建重要日期：calendar=solar 必填 date_solar；calendar=lunar 必填合法农历月日。"""

    type: str = Field(default="birthday")
    title: str | None = Field(default=None, max_length=100)
    calendar: str
    date_solar: date | None = None
    lunar_month: int | None = Field(default=None, ge=1, le=12)
    lunar_day: int | None = Field(default=None, ge=1, le=30)
    lunar_is_leap: bool = False
    yearly: bool = True
    reminder_lead_days: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fields(self) -> "ImportantDateCreate":
        """历法与字段的配套校验（给出可读错误信息）。"""
        if self.type not in DATE_TYPE_VALUES:
            raise ValueError(f"type 必须是 {DATE_TYPE_VALUES} 之一")
        if self.calendar not in CALENDAR_VALUES:
            raise ValueError(f"calendar 必须是 {CALENDAR_VALUES} 之一")
        if self.calendar == "solar" and self.date_solar is None:
            raise ValueError("公历日期必须提供 date_solar")
        if self.calendar == "lunar":
            if self.lunar_month is None or self.lunar_day is None:
                raise ValueError("农历日期必须提供 lunar_month 与 lunar_day")
            if self.date_solar is not None:
                raise ValueError("农历日期不应填写 date_solar")
        if any(days < 0 or days > 365 for days in self.reminder_lead_days):
            raise ValueError("提前提醒天数须在 0-365 之间")
        return self


class ImportantDateUpdate(BaseModel):
    """更新重要日期：全字段可选，仅提交字段生效。"""

    type: str | None = None
    title: str | None = Field(default=None, max_length=100)
    calendar: str | None = None
    date_solar: date | None = None
    lunar_month: int | None = Field(default=None, ge=1, le=12)
    lunar_day: int | None = Field(default=None, ge=1, le=30)
    lunar_is_leap: bool | None = None
    yearly: bool | None = None
    reminder_lead_days: list[int] | None = None

    @model_validator(mode="after")
    def validate_change(self) -> "ImportantDateUpdate":
        """拒绝空更新与非法枚举（历法配套校验在 service 内整体复核）。"""
        dump = self.model_dump(exclude_unset=True)
        if not dump:
            raise ValueError("没有需要更新的字段")
        if dump.get("type") is not None and dump["type"] not in DATE_TYPE_VALUES:
            raise ValueError(f"type 必须是 {DATE_TYPE_VALUES} 之一")
        if dump.get("calendar") is not None and dump["calendar"] not in CALENDAR_VALUES:
            raise ValueError(f"calendar 必须是 {CALENDAR_VALUES} 之一")
        if dump.get("reminder_lead_days") is not None and any(
            days < 0 or days > 365 for days in dump["reminder_lead_days"]
        ):
            raise ValueError("提前提醒天数须在 0-365 之间")
        return self


class DateReminder(BaseModel):
    """进入提醒窗口的重要日期（contacts 域统一的日期提醒输出）。

    lunar_label 仅农历日期有值（"农历三月初三"），展示层直接渲染。
    """

    date_id: int
    date_type: str
    title: str | None
    contact_id: int
    contact_name: str
    next_date: date
    days_left: int
    lunar_label: str | None = None
