"""funds 模块 Pydantic 模式：资金往来的请求/响应契约。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.modules.funds.models import (
    FUND_CATEGORY_VALUES,
    FUND_DIRECTION_VALUES,
    FUND_STATUS_VALUES,
)


class FundFlowCreate(BaseModel):
    """创建资金流水：方向/类别/金额/发生日必填，其余可选。

    status 不开放直接创建：带 due_at 视为需结清（服务端置 pending），否则为 NULL。
    """

    contact_id: int | None = None
    direction: str
    category: str
    amount: str = Field(pattern=r"^\d{1,10}(\.\d{1,2})?$", description="金额字符串，避免浮点误差")
    currency: str = Field(default="CNY", max_length=8)
    occurred_at: date
    due_at: date | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_enums(self) -> "FundFlowCreate":
        """方向与类别必须为字典值。"""
        if self.direction not in FUND_DIRECTION_VALUES:
            raise ValueError(f"direction 必须是 {FUND_DIRECTION_VALUES} 之一")
        if self.category not in FUND_CATEGORY_VALUES:
            raise ValueError(f"category 必须是 {FUND_CATEGORY_VALUES} 之一")
        return self


class FundFlowUpdate(BaseModel):
    """更新资金流水：全字段可选；status 变更由结清流转规则处理（settled_at 自动维护）。"""

    contact_id: int | None = None
    direction: str | None = None
    category: str | None = None
    amount: str | None = Field(default=None, pattern=r"^\d{1,10}(\.\d{1,2})?$")
    currency: str | None = Field(default=None, max_length=8)
    occurred_at: date | None = None
    due_at: date | None = None
    status: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_change(self) -> "FundFlowUpdate":
        """拒绝空更新与非法枚举。"""
        dump = self.model_dump(exclude_unset=True)
        if not dump:
            raise ValueError("没有需要更新的字段")
        if dump.get("direction") is not None and dump["direction"] not in FUND_DIRECTION_VALUES:
            raise ValueError(f"direction 必须是 {FUND_DIRECTION_VALUES} 之一")
        if dump.get("category") is not None and dump["category"] not in FUND_CATEGORY_VALUES:
            raise ValueError(f"category 必须是 {FUND_CATEGORY_VALUES} 之一")
        if dump.get("status") is not None and dump["status"] not in FUND_STATUS_VALUES:
            raise ValueError(f"status 必须是 {FUND_STATUS_VALUES} 之一")
        return self


class FundFlowOut(BaseModel):
    """资金流水输出：金额以字符串回显。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int | None
    direction: str
    category: str
    amount: Decimal | None
    currency: str
    occurred_at: date
    due_at: date | None
    status: str | None
    settled_at: date | None
    description: str | None
    owner_user_id: int
    owner_display_name: str
    visibility: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal | None) -> str | None:
        """Decimal → 定点字符串，如 "2000.00"。"""
        return f"{value:.2f}" if value is not None else None
