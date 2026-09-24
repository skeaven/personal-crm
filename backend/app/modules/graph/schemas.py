"""graph 模块 Pydantic 模式：关系类型字典与关系边的请求/响应契约。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.graph.models import RELATION_GROUP_VALUES


class RelationshipTypeCreate(BaseModel):
    """新增关系类型：组别 + 正向标签（反向可空=对称关系）。"""

    group_name: str
    name: str = Field(max_length=50)
    reverse_name: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_group(self) -> "RelationshipTypeCreate":
        """组别必须为字典值。"""
        if self.group_name not in RELATION_GROUP_VALUES:
            raise ValueError(f"group_name 必须是 {RELATION_GROUP_VALUES} 之一")
        return self


class RelationshipTypeOut(BaseModel):
    """关系类型输出（is_system/kind 供前端联动角色下拉，D15）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    group_name: str
    name: str
    reverse_name: str | None
    is_system: bool = False
    kind: str | None = None


class RelationshipCreate(BaseModel):
    """创建关系边：from 是关系的主体（"A 是 B 的丈夫"则 from=A）。

    系统结构化类型（D15）须带 from_role/to_role（值域校验在服务层按 kind 联动）；
    自定义类型两角色留空。
    """

    from_contact_id: int
    to_contact_id: int
    type_id: int
    from_role: str | None = Field(default=None, max_length=30)
    to_role: str | None = Field(default=None, max_length=30)
    status: str = "active"
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_ends(self) -> "RelationshipCreate":
        """关系边不可自环。"""
        if self.from_contact_id == self.to_contact_id:
            raise ValueError("关系的两端不能是同一个人")
        return self


class RelationshipOut(BaseModel):
    """关系输出（以某联系人为视角的方向归一形态）。

    direction=out 表示视角人物是主体（用正向标签）；in 表示视角人物是客体
    （用反向标签，对称关系回落正向）。前端直接渲染 type_label 即可。
    """

    id: int
    direction: str
    other_contact_id: int
    other_contact_name: str
    other_tier: str
    type_id: int
    type_label: str
    type_name: str
    kind: str | None = None
    # 视角化称谓（D15）：kinship_label 有值时前端优先展示（如"爸爸""岳父"）
    kinship_label: str | None = None
    status: str = "active"
    note: str | None
    owner_user_id: int
    owner_display_name: str
    created_at: datetime


class GraphNodeOut(BaseModel):
    """图数据节点。"""

    id: int
    name: str
    tier: str


class GraphLinkOut(BaseModel):
    """图数据边：source/target 为联系人 id，label 为关系正向标签。"""

    id: int
    source: int
    target: int
    label: str


class GraphDataOut(BaseModel):
    """图数据（主页预留区与图谱页共用）。"""

    nodes: list[GraphNodeOut]
    links: list[GraphLinkOut]


class KinshipStepOut(BaseModel):
    """称谓路径的一跳：途经联系人 + 该跳角色。"""

    contact_id: int
    name: str
    kind: str | None
    role: str | None


class KinshipOut(BaseModel):
    """视角称谓推导结果（D15）：从"我"到目标的最短角色路径。"""

    found: bool
    title: str | None = None
    generation_diff: int | None = None
    path: list[KinshipStepOut] = []
