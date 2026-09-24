"""records 模块 Pydantic 模式：活动（含参与者）与任务的请求/响应契约。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.records.models import TASK_STATUS_VALUES

# 参与者名单容量上限：家庭聚会量级（几十人）足够，同时防御误传超长列表
MAX_PARTICIPANTS = 50


class ParticipantIn(BaseModel):
    """参与者名单字段：联系人 id 列表，去重由数据库唯一约束兜底。"""

    participant_ids: list[int] = Field(default_factory=list, max_length=MAX_PARTICIPANTS)


class ActivityCreate(BaseModel):
    """创建活动：标题必填，时间/地点/详情可选，参与者即刻挂入。"""

    title: str = Field(max_length=200)
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=200)
    detail: str | None = None
    participant_ids: list[int] = Field(default_factory=list, max_length=MAX_PARTICIPANTS)


class ActivityUpdate(ParticipantIn):
    """更新活动：全字段可选，仅提交的字段生效；participant_ids 提交即全量替换。"""

    title: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=200)
    detail: str | None = None

    @model_validator(mode="after")
    def validate_any_change(self) -> "ActivityUpdate":
        """拒绝空更新请求，避免无意义的写放大。"""
        fields = self.model_dump(exclude={"participant_ids"}, exclude_unset=True)
        if not fields and "participant_ids" not in self.model_fields_set:
            raise ValueError("没有需要更新的字段")
        return self


class ActivityOut(BaseModel):
    """活动输出：participants 以 id 列表回显（前端按需再查联系人详情）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    occurred_at: datetime | None
    location: str | None
    detail: str | None
    owner_user_id: int
    owner_display_name: str
    visibility: str
    created_at: datetime
    updated_at: datetime
    participant_ids: list[int] = []


class TaskCreate(BaseModel):
    """创建任务：标题必填，联系人/截止时间可选。"""

    title: str = Field(max_length=200)
    contact_id: int | None = None
    detail: str | None = None
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    """更新任务：全字段可选；status=done 由服务端盖 completed_at。"""

    title: str | None = Field(default=None, max_length=200)
    contact_id: int | None = None
    detail: str | None = None
    due_at: datetime | None = None
    status: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "TaskUpdate":
        """校验 status 枚举与空更新，给出可读错误。"""
        if self.status is not None and self.status not in TASK_STATUS_VALUES:
            raise ValueError(f"status 必须是 {TASK_STATUS_VALUES} 之一")
        if not self.model_dump(exclude_unset=True):
            raise ValueError("没有需要更新的字段")
        return self


class TaskOut(BaseModel):
    """任务输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    contact_id: int | None
    detail: str | None
    due_at: datetime | None
    status: str
    completed_at: datetime | None
    owner_user_id: int
    owner_display_name: str
    visibility: str
    created_at: datetime
    updated_at: datetime
