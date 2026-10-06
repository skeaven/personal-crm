"""records 模块 Pydantic 模式：活动（含参与者）与任务的请求/响应契约。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.records.models import TASK_STATUS_VALUES

# 参与者名单容量上限：家庭聚会量级（几十人）足够，同时防御误传超长列表
MAX_PARTICIPANTS = 50

# 每个活动的图片上限：家庭相册量级足够，同时防御超长列表
MAX_IMAGES = 20


class ImageRefIn(BaseModel):
    """图片提交项：保留已有图给 id，新增图给 temp_path；数组顺序即展示顺序。"""

    id: int | None = None
    temp_path: str | None = None

    @model_validator(mode="after")
    def validate_exactly_one(self) -> "ImageRefIn":
        """id 与 temp_path 必须恰好提供一个，消除"两个都给"的歧义。"""
        if (self.id is None) == (self.temp_path is None):
            raise ValueError("图片项必须且只能给 id 或 temp_path 之一")
        return self


class ActivityImageOut(BaseModel):
    """活动图片输出：前端拿 id 拼鉴权读取地址，按 sort_order 升序展示。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int


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
    images: list[ImageRefIn] = Field(default_factory=list, max_length=MAX_IMAGES)


class ActivityUpdate(ParticipantIn):
    """更新活动：全字段可选，仅提交的字段生效；participant_ids 提交即全量替换。"""

    title: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=200)
    detail: str | None = None
    images: list[ImageRefIn] | None = Field(default=None, max_length=MAX_IMAGES)

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
    images: list[ActivityImageOut] = []


class NoteCreate(BaseModel):
    """创建备注：必须挂在可读联系人下（当前版本备注均归属联系人，自由笔记暂不开放）。"""

    contact_id: int
    content: str = Field(min_length=1)


class NoteUpdate(BaseModel):
    """更新备注：仅正文可改；归属联系人不可迁移，挪动归属应删了重记。"""

    content: str = Field(min_length=1)


class NoteOut(BaseModel):
    """备注输出：owner_display_name 供家人场景显示"谁记的"。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int | None
    content: str
    owner_user_id: int
    owner_display_name: str
    visibility: str
    created_at: datetime
    updated_at: datetime


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
