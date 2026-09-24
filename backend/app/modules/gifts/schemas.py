"""gifts 模块 Pydantic 模式：礼物往来与愿望清单的请求/响应契约。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.modules.gifts.models import GIFT_DIRECTION_VALUES, WISHLIST_STATUS_VALUES


class _MoneySerializerMixin(BaseModel):
    """金额序列化混入：NUMERIC 列以字符串回显（与请求对称，避免 JS 浮点误差）。"""

    amount: Decimal | None = None

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal | None) -> str | None:
        """Decimal → 定点字符串，如 "388.00"。"""
        return f"{value:.2f}" if value is not None else None


class GiftCreate(BaseModel):
    """创建礼物往来：方向与名称必填，其余可选。"""

    contact_id: int | None = None
    direction: str
    title: str = Field(max_length=200)
    occasion: str | None = Field(default=None, max_length=100)
    # 金额用字符串传输，避免 JS 浮点误差；正则限制为最多 10 位整数 + 2 位小数
    amount: str | None = Field(default=None, pattern=r"^\d{1,10}(\.\d{1,2})?$")
    currency: str = Field(default="CNY", max_length=8)
    given_at: date | None = None
    link: str | None = Field(default=None, max_length=500)
    description: str | None = None

    @model_validator(mode="after")
    def validate_direction(self) -> "GiftCreate":
        """方向必须为 given/received。"""
        if self.direction not in GIFT_DIRECTION_VALUES:
            raise ValueError(f"direction 必须是 {GIFT_DIRECTION_VALUES} 之一")
        return self


class GiftUpdate(BaseModel):
    """更新礼物：全字段可选，仅提交字段生效。"""

    contact_id: int | None = None
    direction: str | None = None
    title: str | None = Field(default=None, max_length=200)
    occasion: str | None = Field(default=None, max_length=100)
    amount: str | None = Field(default=None, pattern=r"^\d{1,10}(\.\d{1,2})?$")
    currency: str | None = Field(default=None, max_length=8)
    given_at: date | None = None
    link: str | None = Field(default=None, max_length=500)
    description: str | None = None

    @model_validator(mode="after")
    def validate_change(self) -> "GiftUpdate":
        """拒绝空更新与非法方向。"""
        dump = self.model_dump(exclude_unset=True)
        if not dump:
            raise ValueError("没有需要更新的字段")
        if dump.get("direction") is not None and dump["direction"] not in GIFT_DIRECTION_VALUES:
            raise ValueError(f"direction 必须是 {GIFT_DIRECTION_VALUES} 之一")
        return self


class GiftOut(_MoneySerializerMixin):
    """礼物输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int | None
    direction: str
    title: str
    occasion: str | None
    currency: str
    given_at: date | None
    link: str | None
    description: str | None
    owner_user_id: int
    owner_display_name: str
    visibility: str
    created_at: datetime
    updated_at: datetime


class WishlistCreate(BaseModel):
    """创建愿望清单项：标题必填，状态默认 open。"""

    contact_id: int | None = None
    title: str = Field(max_length=200)
    amount: str | None = Field(default=None, pattern=r"^\d{1,10}(\.\d{1,2})?$")
    currency: str = Field(default="CNY", max_length=8)
    link: str | None = Field(default=None, max_length=500)
    description: str | None = None
    status: str = "open"
    target_date: date | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "WishlistCreate":
        """状态必须为 open/purchased/given。"""
        if self.status not in WISHLIST_STATUS_VALUES:
            raise ValueError(f"status 必须是 {WISHLIST_STATUS_VALUES} 之一")
        return self


class WishlistUpdate(BaseModel):
    """更新愿望：全字段可选；状态推进不在此处做（送出走 convert 专用端点）。"""

    contact_id: int | None = None
    title: str | None = Field(default=None, max_length=200)
    amount: str | None = Field(default=None, pattern=r"^\d{1,10}(\.\d{1,2})?$")
    currency: str | None = Field(default=None, max_length=8)
    link: str | None = Field(default=None, max_length=500)
    description: str | None = None
    status: str | None = None
    target_date: date | None = None

    @model_validator(mode="after")
    def validate_change(self) -> "WishlistUpdate":
        """拒绝空更新与非法状态。"""
        dump = self.model_dump(exclude_unset=True)
        if not dump:
            raise ValueError("没有需要更新的字段")
        if dump.get("status") is not None and dump["status"] not in WISHLIST_STATUS_VALUES:
            raise ValueError(f"status 必须是 {WISHLIST_STATUS_VALUES} 之一")
        return self


class WishlistOut(_MoneySerializerMixin):
    """愿望输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int | None
    title: str
    currency: str
    link: str | None
    description: str | None
    status: str
    target_date: date | None
    converted_gift_id: int | None
    owner_user_id: int
    owner_display_name: str
    visibility: str
    created_at: datetime
    updated_at: datetime


class WishlistConvertOut(BaseModel):
    """转礼物结果：新礼物 + 更新后的愿望（前端一次拿到两份数据刷新两个列表）。"""

    gift: GiftOut
    item: WishlistOut
