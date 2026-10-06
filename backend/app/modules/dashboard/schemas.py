"""dashboard 模块 Pydantic 模式：待办聚合与联系人时间线的输出契约。"""

from datetime import date, datetime

from pydantic import BaseModel

# 待办来源（聚合五源；agent/MCP 创建的任务天然归属 task 源）
TODO_SOURCE_VALUES = ("task", "wish", "repayment", "activity", "birthday")

# 待办分桶：todo 未过期 / overdue 已过期 / done 已完成 / all 并集
TODO_BUCKET_VALUES = ("todo", "overdue", "done", "all")

# 时间线来源（详情页竖向时间线；随模块迭代可继续扩充，如生日事件）
TIMELINE_SOURCE_VALUES = ("gift", "fund", "activity", "note")


class TodoItemOut(BaseModel):
    """统一待办项：五个来源归一为同一形状，前端按 source 渲染徽标与跳转。

    days_left 负数表示已过期天数；生日永不过期（滚动到明年），恒为非负。
    bucket 是该项实际归属（todo/overdue/done），供"全部"页签区分展示。
    """

    source: str
    ref_id: int
    title: str
    contact_id: int | None = None
    contact_name: str | None = None
    due_date: date | None = None
    days_left: int | None = None
    lunar_label: str | None = None
    bucket: str


class TimelineItemOut(BaseModel):
    """时间线条目：四源（礼物/资金/活动/备注）归一形状，前端按 source 渲染图标与文案。

    amount 以字符串回显（NUMERIC 精度）；direction 保留原始方向（送出/流出），
    occurred_at 为归一化的排序时刻（日期源加日内偏移，保证跨源稳定）。
    """

    source: str
    ref_id: int
    occurred_at: datetime
    title: str
    summary: str | None = None
    amount: str | None = None
    direction: str | None = None
    extra_label: str | None = None


class TimelineOut(BaseModel):
    """时间线响应：items 按发生时刻倒序全量返回（个人 CRM 量级，不做服务端分页）。"""

    contact_id: int
    items: list[TimelineItemOut]
