"""ai 模块工具注册表：MCP 工具的单一实现源（D11）。

每个工具 = 名称 + 描述 + 风险档位（read 直执行 / write_queue 进确认队列）
+ 入参 schema（Pydantic）+ 处理函数（以发起用户身份执行，D7）。
MCP 端点与内部 agent 都从这里消费同一份清单，禁止另设工具路径。
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError, NotFoundError, ValidationError
from app.modules.contacts import service as contacts_service
from app.modules.dashboard import service as dashboard_service
from app.modules.records import service as records_service

# ---------- 入参 schema ----------


class ListContactsArgs(BaseModel):
    """名册列表入参：不传任何条件即全量（受调用者可读范围约束）。"""

    tier: Literal["direct", "edge"] | None = Field(default=None, description="层级过滤")
    search: str | None = Field(default=None, description="姓名/昵称/单位关键字")
    activity: Literal["recent_30d", "stale_180d"] | None = Field(
        default=None, description="recent_30d=近 30 天联系过；stale_180d=超半年未联系"
    )


class GetContactArgs(BaseModel):
    """读单人完整资料入参（含重要日期）。"""

    contact_id: int


class SemanticSearchArgs(BaseModel):
    """语义搜索入参（自然语言描述，不限关键字）。"""

    query: str = Field(min_length=1, description="自然语言描述，如：谁爱钓鱼、婚礼随礼记录")


class EmptyArgs(BaseModel):
    """无参工具的占位 schema。"""

    pass


class KinshipArgs(BaseModel):
    """kinship_of 工具入参：目标联系人 id（list_contacts 可拿到）。"""

    contact_id: int


class ContactTimelineArgs(BaseModel):
    """联系人时间线入参。"""

    contact_name: str = Field(min_length=1, description="联系人姓名或昵称")


class CreateTaskArgs(BaseModel):
    """建待办入参（写入确认队列）。"""

    title: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, description="关联联系人（可选）")
    due_date: str | None = Field(default=None, description="截止日 YYYY-MM-DD（可选）")


class CreateActivityArgs(BaseModel):
    """记活动入参（写入确认队列）。"""

    title: str = Field(min_length=1, max_length=200)
    occurred_date: str = Field(description="活动日期 YYYY-MM-DD")
    participant_names: list[str] = Field(default_factory=list, description="参与者姓名/昵称")
    location: str | None = Field(default=None, max_length=200)


class CreateContactArgs(BaseModel):
    """建联系人入参（写入确认队列）：名片/截图上读得到的字段，全部可选。"""

    tier: Literal["direct", "edge"] = Field(
        default="direct", description="direct=直接联系人（默认）；信息量少给 edge"
    )
    name: str = Field(default="", max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    organization: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    qq: str | None = Field(default=None, max_length=30)
    wechat: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=120)
    school_name: str | None = Field(default=None, max_length=100)
    bio: str | None = None
    location: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_name_presence(self) -> "CreateContactArgs":
        """与 ContactCreate 同一最小信息集：姓名、昵称至少一项，否则没法定位到人。"""
        if not any([self.name.strip(), (self.nickname or "").strip()]):
            raise ValueError("姓名、昵称至少填写一项")
        return self


# ---------- 查询类工具（read，直执行） ----------


def _format_todo(item: Any) -> str:
    """待办条目的 LLM 友好单行格式。"""
    when = item.due_date or "无期限"
    return f"- [{item.source}] {item.title}（{when}）"


async def _run_list_contacts(db: AsyncSession, user, args: ListContactsArgs) -> str:
    """名册列表：每条给 id + 展示名 + 可区分字段，供模型复述候选给用户确认。"""
    contacts = await contacts_service.list_contacts(
        db, user, tier=args.tier, search=args.search, activity=args.activity
    )
    if not contacts:
        return "没有符合条件的联系人"
    lines = [
        f"- {c.display_name}（id={c.id}，{'边缘' if c.tier == 'edge' else '直接'}联系人"
        f"{'，单位：' + c.organization if c.organization else ''}，{c.owner_display_name} 记录）"
        for c in contacts
    ]
    return f"共 {len(contacts)} 位：\n" + "\n".join(lines)


async def _run_get_contact(db: AsyncSession, user, args: GetContactArgs) -> str:
    """读单人完整资料 + 重要日期：改之前的回读入口（看得到现状才谈得上改）。"""
    try:
        detail = await contacts_service.get_contact(db, user, args.contact_id)
    except NotFoundError:
        # 不可读与不存在给同一句话，不泄露存在性（判权口径见 permission.py）
        return f"没有找到 id={args.contact_id} 的联系人"
    fields = [
        ("姓名", detail.name),
        ("昵称", detail.nickname),
        ("单位", detail.organization),
        ("电话", detail.phone),
        ("微信", detail.wechat),
        ("QQ", detail.qq),
        ("邮箱", detail.email),
        ("毕业院校", detail.school_name),
        ("现居地", detail.current_address),
        ("家庭地址", detail.family_address),
        ("兴趣爱好", detail.hobbies),
        ("所在地", detail.location),
        ("备注", detail.bio),
        ("层级", "边缘" if detail.tier == "edge" else "直接"),
    ]
    lines = [f"{label}：{value}" for label, value in fields if value]
    if detail.dates:
        lines.append("重要日期：")
        for item in detail.dates:
            when = (
                item.date_solar.isoformat()
                if item.date_solar
                else f"农历 {item.lunar_month} 月 {item.lunar_day} 日"
            )
            lead = "、".join(str(day) for day in item.reminder_lead_days)
            lines.append(f"  - id={item.id} {item.type} {when}（提前 {lead} 天提醒）")
    return f"联系人 id={detail.id} 的资料：\n" + "\n".join(lines)


async def _run_kinship_of(db: AsyncSession, user, args: KinshipArgs) -> str:
    """回答「某人是我什么人」：从「我」出发的角色路径 + 中文称谓。"""
    from app.modules.graph import service as graph_service

    result = await graph_service.kinship_of(db, user, args.contact_id)
    if not result.found:
        return "推不出来：要么账号还没绑定「我是谁」，要么图上没有连通的路径"
    if not result.title:
        chain = " → ".join(step.name for step in result.path)
        return f"能连到（{chain}），但没有对应的中文称谓规则"
    gen = result.generation_diff or 0
    gen_label = {1: "长辈", -1: "晚辈", 0: "同辈"}.get(gen, f"辈分差 {gen:+d}")
    chain = " → ".join(f"{step.name}（{step.kind}:{step.role}）" for step in result.path)
    return f"「{result.title}」（{gen_label}）。关系链：{chain}"


async def _run_upcoming_todos(db: AsyncSession, user, args: EmptyArgs) -> str:
    """返回临近事项（待办看板全部桶，倒序前 15 条）。"""
    board = await dashboard_service.build_todo_board(db, user, "all")
    if not board:
        return "当前没有任何待办事项"
    return "临近事项：\n" + "\n".join(_format_todo(item) for item in board[:15])


async def _resolve_contact_by_name(
    db: AsyncSession, user, name: str
) -> tuple[int, str] | None:
    """按展示名/昵称解析联系人；多命中取第一个（LLM 会先经 list_contacts 消歧）。"""
    contacts = await contacts_service.list_contacts(db, user, tier=None, search=name)
    if not contacts:
        return None
    exact = [c for c in contacts if c.display_name == name]
    chosen = exact[0] if exact else contacts[0]
    return chosen.id, chosen.display_name


async def _run_contact_timeline(db: AsyncSession, user, args: ContactTimelineArgs) -> str:
    """按名字查联系人的最近往来（时间线聚合前 10 条）。"""
    resolved = await _resolve_contact_by_name(db, user, args.contact_name)
    if resolved is None:
        return f"没有找到「{args.contact_name}」"
    contact_id, display_name = resolved
    timeline = await dashboard_service.build_contact_timeline(db, user, contact_id)
    if not timeline.items:
        return f"{display_name} 暂无往来记录"
    lines = []
    for item in timeline.items[:10]:
        day = item.occurred_at.date().isoformat()
        amount = f"，{item.amount} 元" if item.amount else ""
        lines.append(f"- {day} [{item.source}] {item.title}{amount}")
    return f"{display_name} 的最近往来：\n" + "\n".join(lines)


async def _run_semantic_search(db: AsyncSession, user, args: SemanticSearchArgs) -> str:
    """语义搜索：跨联系人/活动/礼物/资金/备注按含义检索（非关键字匹配）。"""
    from app.modules.ai import semantic as semantic_service

    results = await semantic_service.search(db, user, args.query, limit=8)
    if not results:
        return "没有语义相关的记录（如果刚录入数据，请先在设置页重建索引）"
    type_label = {
        "contact": "联系人", "activity": "活动", "gift": "礼物",
        "fund": "资金", "note": "备注",
    }
    lines = [
        f"- [{type_label.get(r['entity_type'], r['entity_type'])}] {r['content']}"
        for r in results
    ]
    return "语义相关的记录：\n" + "\n".join(lines)


async def _run_queue_create_contact(db: AsyncSession, user, args: CreateContactArgs) -> str:
    """建联系人提议入队：payload 即联系人字段，同名拦截延后到确认执行时。"""
    from app.modules.ai import pending as pending_service

    payload: dict[str, Any] = {
        "tier": args.tier,
        "name": args.name,
    }
    for key in (
        "nickname", "organization", "phone", "qq",
        "wechat", "email", "school_name", "bio", "location",
    ):
        value = getattr(args, key)
        if value:
            payload[key] = value
    action = await pending_service.propose(db, user, "create_contact", payload)
    suffix = f"（{args.nickname}）" if args.nickname else ""
    return (
        f"已生成联系人提议（编号 {action.id}，待确认）：{args.name}{suffix}。"
        f"需要用户在界面确认后才会真正创建。"
    )


async def _run_stats(db: AsyncSession, user, args: EmptyArgs) -> str:
    """名册统计概览（含名单：数字与"是谁"一步给全，模型无需再逐个搜索）。"""
    report = await contacts_service.activity_report(db, user)
    tasks = await records_service.list_tasks(db, user, status="todo")

    stale_text = "、".join(
        f"{name}（{note}）" for name, note in report["stale_names"]
    ) or "无"
    recent_text = "、".join(report["recent_names"]) or "无"
    return (
        f"联系人共 {report['total_contacts']} 位；"
        f"近 30 天联系过 {report['recent_contacted']} 位：{recent_text}；"
        f"超过半年未联系 {report['stale_half_year']} 位：{stale_text}；"
        f"进行中待办 {len(tasks)} 件。"
    )


# ---------- 写入类工具（write_queue，进确认队列不直接落库） ----------


async def _run_queue_create_task(db: AsyncSession, user, args: CreateTaskArgs) -> str:
    """建待办提议入队。"""
    from app.modules.ai import pending as pending_service

    payload: dict[str, Any] = {"title": args.title}
    if args.contact_name:
        payload["contact_name"] = args.contact_name
    if args.due_date:
        payload["due_at"] = args.due_date
    action = await pending_service.propose(db, user, "create_task", payload)
    return (
        f"已生成待办提议（编号 {action.id}，待确认）：「{args.title}」。"
        f"需要用户在界面确认后才会真正创建。"
    )


async def _run_queue_create_activity(db: AsyncSession, user, args: CreateActivityArgs) -> str:
    """记活动提议入队（含参与者名单，确认时解析为联系人）。"""
    from app.modules.ai import pending as pending_service

    payload: dict[str, Any] = {
        "title": args.title,
        "occurred_at": args.occurred_date,
        "participant_names": args.participant_names,
    }
    if args.location:
        payload["location"] = args.location
    action = await pending_service.propose(db, user, "create_activity", payload)
    return (
        f"已生成活动提议（编号 {action.id}，待确认）：「{args.title}」于 {args.occurred_date}。"
        f"需要用户在界面确认后才会真正创建。"
    )


# ---------- 注册表 ----------


@dataclass(frozen=True)
class AiTool:
    """MCP 工具三元组（D11）：schema + 风险档位 + 处理函数。"""

    name: str
    label: str  # 中文名：确认面板渲染用，经 /ai/tools 下发（不进 MCP 协议形状）
    description: str
    risk: str
    args_schema: type[BaseModel]
    run: Any


ALL_TOOLS: list[AiTool] = [
    AiTool(
        name="list_contacts",
        label="查名册",
        description=(
            "列出可读联系人（可按层级/关键字/联系活跃度过滤），每条带 id；"
            "找人、看名册、以及任何后续要按 id 操作的场景都先用它拿 id"
        ),
        risk="read",
        args_schema=ListContactsArgs,
        run=_run_list_contacts,
    ),
    AiTool(
        name="get_contact",
        label="读联系人资料",
        description=(
            "按 id 读某位联系人的完整资料与重要日期；**改任何联系人字段之前必须先用它回读现状**"
        ),
        risk="read",
        args_schema=GetContactArgs,
        run=_run_get_contact,
    ),
    AiTool(
        name="kinship_of",
        label="查称谓",
        description=(
            "查某位联系人是「我」的什么人（中文称谓+辈分）；先用 list_contacts 拿 id"
        ),
        risk="read",
        args_schema=KinshipArgs,
        run=_run_kinship_of,
    ),
    AiTool(
        name="get_upcoming_todos",
        label="查临近事项",
        description="查看临近的事项：生日提醒、待办任务、还款、心愿、活动",
        risk="read",
        args_schema=EmptyArgs,
        run=_run_upcoming_todos,
    ),
    AiTool(
        name="get_contact_timeline",
        label="查往来",
        description="按名字查某位联系人的最近往来（礼物/资金/活动时间线）",
        risk="read",
        args_schema=ContactTimelineArgs,
        run=_run_contact_timeline,
    ),
    AiTool(
        name="semantic_search",
        label="语义搜索",
        description="按含义搜索所有记录（联系人/活动/礼物/资金/备注），"
                    "适合模糊描述如「谁爱钓鱼」「孩子升学」；精确关键字搜索用 list_contacts",
        risk="read",
        args_schema=SemanticSearchArgs,
        run=_run_semantic_search,
    ),
    AiTool(
        name="get_stats",
        label="查统计",
        description="查看名册统计与名单：总数、近 30 天联系过的人、"
                    "超过半年未联系的人（含姓名）、待办数",
        risk="read",
        args_schema=EmptyArgs,
        run=_run_stats,
    ),
    AiTool(
        name="create_task",
        label="建待办",
        description="创建一条待办任务（需用户确认后生效）",
        risk="write_queue",
        args_schema=CreateTaskArgs,
        run=_run_queue_create_task,
    ),
    AiTool(
        name="create_activity",
        label="记活动",
        description="记录一次社交活动，可附参与者名单（需用户确认后生效）",
        risk="write_queue",
        args_schema=CreateActivityArgs,
        run=_run_queue_create_activity,
    ),
    AiTool(
        name="create_contact",
        label="建联系人",
        description=(
            "录入一个新联系人（口述或名片/截图识别均可，需用户确认后生效）；"
            "提议前先用 list_contacts 查同名"
        ),
        risk="write_queue",
        args_schema=CreateContactArgs,
        run=_run_queue_create_contact,
    ),
]

_TOOLS_BY_NAME = {tool.name: tool for tool in ALL_TOOLS}


def get_tool(name: str) -> AiTool | None:
    """按名字取工具定义；未注册返回 None。"""
    return _TOOLS_BY_NAME.get(name)


def build_args(tool: AiTool, data: dict) -> Any:
    """用工具 schema 校验并构造入参（MCP/agent 调用入口共用）。"""
    return tool.args_schema(**data)


async def resolve_contact_name(db: AsyncSession, user, name: str) -> int | None:
    """执行器用的联系人名解析（找不到返回 None，由执行器决定失败语义）。"""
    resolved = await _resolve_contact_by_name(db, user, name)
    return resolved[0] if resolved else None


def parse_iso_date(value: str, field_name: str) -> date:
    """ISO 日期字符串解析（执行器用），非法即业务错误。"""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name} 不是合法日期（YYYY-MM-DD）") from exc


def ensure_positive_int(value: int, field_name: str) -> int:
    """正整数断言（执行器用）。"""
    if value <= 0:
        raise BusinessError(f"{field_name} 必须为正数")
    return value
