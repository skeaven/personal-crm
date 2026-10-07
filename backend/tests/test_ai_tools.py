"""AI 工具注册表测试：查询直执行（可读范围隔离）、写入进确认队列。"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.db import get_session_factory
from app.modules.ai import registry
from app.modules.ai.registry import build_args, get_tool
from tests.factories import (
    create_activity_for,
    create_contact_for,
    create_date_for,
    create_family_user,
    create_gift_for,
    create_task_for,
)

pytestmark = pytest.mark.asyncio


async def _run_tool(db, user, tool_name: str, **args) -> str:
    """按名字执行注册表工具（agent 与 MCP 端点共用的同一入口）。

    形参名用 tool_name 而非 name：联系人的 name 字段会经 **args 传进来，用 name 会撞车。
    """
    tool = get_tool(tool_name)
    assert tool is not None, f"工具 {tool_name} 未注册"
    return await tool.run(db, user, build_args(tool, args))


async def test_list_contacts_tool(db_session, make_user):
    """名册工具：命中昵称，输出含展示名（agent 后续引用）。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, name="陈建国", nickname="老爸")

    out = await _run_tool(db_session, demo, "list_contacts", search="老爸")
    assert "老爸" in out


async def test_list_contacts_respects_visibility(db_session, make_user):
    """名册只出现在发起用户可读范围内（私密联系人不出现在家人列表里）。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    await create_contact_for(demo, name="周明", visibility="private")
    tong, _ = await create_family_user(family_id=demo.family_id, username="tong2")

    out = await _run_tool(db_session, tong, "list_contacts", search="周")
    assert "周明" not in out


async def test_list_contacts_returns_ids_and_distinguishing_fields(db_session, make_user):
    """每条都带 id 与可区分字段：多命中时模型要能复述候选给用户确认（spec §3.4）。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, name="唐琴", organization="极星科技")
    await create_contact_for(demo, name="唐琴", organization="另一家")

    text = await _run_tool(db_session, demo, "list_contacts", search="唐琴")

    assert text.count("id=") == 2
    assert "极星科技" in text and "另一家" in text


async def test_get_contact_returns_full_fields_and_dates(db_session, make_user):
    """get_contact 是改之前的回读入口：字段与重要日期一次给全。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="唐琴", phone="13800000000")
    await create_date_for(
        demo, contact.id, type="birthday", calendar="lunar", lunar_month=9, lunar_day=24
    )

    text = await _run_tool(db_session, demo, "get_contact", contact_id=contact.id)

    assert "唐琴" in text
    assert "13800000000" in text
    assert "农历" in text


async def test_get_contact_of_unreadable_contact_reports_not_found(db_session, make_user):
    """别人的私密联系人不可读：报"没有找到"，不泄露它是否存在。"""
    owner, _ = await make_user(username="owner")
    other, _ = await make_user(username="other", family_id=owner.family_id)
    secret = await create_contact_for(owner, name="私密人", visibility="private")

    text = await _run_tool(db_session, other, "get_contact", contact_id=secret.id)

    assert "没有找到" in text
    assert "私密人" not in text


async def test_search_contacts_is_gone(db_session, make_user):
    """search_contacts 已合并进 list_contacts（spec §3.5）：按名寻址的入口不应存在。"""
    assert get_tool("search_contacts") is None


async def test_get_upcoming_todos_tool(db_session, make_user):
    """待办工具：返回待办标题与剩余天数。"""
    demo, _ = await make_user(username="demo")
    await create_task_for(
        demo, title="给老爸买礼物", due_at=datetime.now(UTC) + timedelta(days=3)
    )
    out = await _run_tool(db_session, demo, "get_upcoming_todos")
    assert "给老爸买礼物" in out


async def test_contact_timeline_tool(db_session, make_user):
    """时间线工具：按名字查联系人并返回往来记录；无命中给出可读提示。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国", nickname="老爸")
    await create_gift_for(
        demo, contact_id=father.id, direction="given", title="按摩仪", given_at=date(2026, 9, 1)
    )

    out = await _run_tool(db_session, demo, "get_contact_timeline", contact_name="老爸")
    assert "按摩仪" in out

    miss = await _run_tool(db_session, demo, "get_contact_timeline", contact_name="不存在的人")
    assert "没有找到" in miss


async def test_write_tools_go_to_queue(db_session, make_user):
    """写入工具不直接落库：进 pending 队列，返回待确认提示。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, name="陈建国", nickname="老爸")

    out = await _run_tool(
        db_session, demo, "create_task",
        title="给老爸打电话", contact_name="老爸", due_date="2026-09-25",
    )
    assert "待确认" in out

    from sqlalchemy import func, select

    from app.modules.ai.models import PendingAction
    from app.modules.records.models import Task

    pending = (
        await db_session.execute(
            select(func.count()).select_from(PendingAction).where(PendingAction.status == "pending")
        )
    ).scalar()
    assert pending == 1
    tasks = (await db_session.execute(select(func.count()).select_from(Task))).scalar()
    assert tasks == 0  # 未确认前不落业务表

    out2 = await _run_tool(
        db_session, demo, "create_activity",
        title="家庭聚餐", occurred_date="2026-09-28",
        participant_names=["老爸"],
    )
    assert "待确认" in out2


async def test_activity_participants_in_timeline(db_session, make_user):
    """时间线工具覆盖活动来源（活动-参与者关联）。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国", nickname="老爸")
    await create_activity_for(
        demo, title="旧聚餐", occurred_at=datetime.now(UTC),
        participant_contact_ids=[father.id],
    )
    out = await _run_tool(db_session, demo, "get_contact_timeline", contact_name="老爸")
    assert "旧聚餐" in out


async def test_kinship_of_tool(db_session, make_user):
    """称谓工具：从绑定的"我"推导两跳称谓（妈妈的哥哥=舅舅）。"""
    demo, _ = await make_user(username="demo")
    from sqlalchemy import select

    from app.modules.auth.models import User
    from app.modules.graph.models import Relationship, RelationshipType

    mother = await create_contact_for(demo, name="李秀", gender="female")
    uncle = await create_contact_for(demo, name="李大勇", gender="male")
    me = await create_contact_for(demo, name="陈小澄", gender="male")

    factory = get_session_factory()
    async with factory() as session:
        user = (await session.execute(
            select(User).where(User.id == demo.id)
        )).scalar_one()
        user.contact_id = me.id
        session.add(RelationshipType(
            group_name="family", name="父母-子女", is_system=True, kind="parent"
        ))
        session.add(RelationshipType(
            group_name="family", name="兄弟姐妹", is_system=True, kind="sibling"
        ))
        await session.commit()
        types = (await session.execute(
            select(RelationshipType).where(RelationshipType.is_system)
        )).scalars().all()
        by_kind = {t.kind: t.id for t in types}
        session.add(Relationship(
            from_contact_id=mother.id, to_contact_id=me.id, type_id=by_kind["parent"],
            from_role="mother", to_role="son", owner_user_id=demo.id, family_id=demo.family_id,
        ))
        session.add(Relationship(
            from_contact_id=uncle.id, to_contact_id=mother.id, type_id=by_kind["sibling"],
            from_role="elder_brother", to_role="younger_sister",
            owner_user_id=demo.id, family_id=demo.family_id,
        ))
        await session.commit()

    # tool 走 db_session 的 user 对象（与 factory 会话不同步），手动补绑定状态
    demo.contact_id = me.id
    out = await _run_tool(db_session, demo, "kinship_of", contact_id=uncle.id)
    assert "舅舅" in out
    assert "长辈" in out


async def test_create_contact_tool_queues_proposal(db_session, make_user):
    """create_contact 进确认队列、不触达联系人表；卡片字段原样进 payload。"""
    demo, _ = await make_user(username="demo")

    out = await _run_tool(
        db_session, demo, "create_contact",
        name="王", nickname="王姨", organization="某某中学", phone="13800000000",
    )

    assert "提议" in out

    from sqlalchemy import select

    from app.modules.ai.models import PendingAction

    rows = list((await db_session.execute(select(PendingAction))).scalars())
    assert len(rows) == 1
    assert rows[0].tool_name == "create_contact"
    assert rows[0].payload["tier"] == "direct"
    assert rows[0].payload["phone"] == "13800000000"
    # 钉住工具契约：姓名走单字段，且回执文案把昵称以括号形式跟随（D23）
    assert rows[0].payload["name"] == "王"
    assert "王（王姨）" in out
    assert rows[0].payload["organization"] == "某某中学"


async def test_create_contact_rejects_unknown_tier(db_session, make_user):
    """tier 只接受 direct/edge：非法值必须在工具入口被 schema 拦下。

    否则它会一路进 propose，到用户点「确认执行」时在 ContactCreate 炸成 500——
    而 ValidationError 不是 BusinessError，approve 接不住，提议永远卡在 pending。
    """
    from pydantic import ValidationError

    demo, _ = await make_user(username="demo")

    with pytest.raises(ValidationError):
        await _run_tool(db_session, demo, "create_contact", name="王", tier="vip")


async def test_every_tool_has_label():
    """每个工具都有中文名：确认面板靠它渲染，前端不再自己维护一份映射。"""
    missing = [tool.name for tool in registry.ALL_TOOLS if not tool.label.strip()]
    assert missing == [], f"以下工具缺 label：{missing}"


async def test_tools_endpoint_exposes_label(client, login_headers, make_user):
    """GET /ai/tools 下发 label——它是前端渲染确认面板的唯一来源。"""
    _, password = await make_user(username="demo")
    headers = await login_headers("demo", password)

    response = await client.get("/api/v1/ai/tools", headers=headers)

    assert response.status_code == 200
    items = response.json()
    assert items, "工具清单不应为空"
    assert all(item["label"] for item in items), "每个工具都必须带 label"
