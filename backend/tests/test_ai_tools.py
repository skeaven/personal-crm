"""AI 工具注册表测试：查询直执行（可读范围隔离）、写入进确认队列。"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.db import get_session_factory
from app.modules.ai import registry
from app.modules.ai.registry import build_args, get_tool
from tests.factories import (
    create_activity_for,
    create_contact_for,
    create_family_user,
    create_gift_for,
    create_task_for,
)

pytestmark = pytest.mark.asyncio


async def _run_tool(db, user, name: str, **args) -> str:
    """按名字执行注册表工具（agent 与 MCP 端点共用的同一入口）。"""
    tool = get_tool(name)
    assert tool is not None, f"工具 {name} 未注册"
    return await tool.run(db, user, build_args(tool, args))


async def test_registry_completeness(client, make_user):
    """注册表：首批工具齐全、名字唯一、风险档位合法。"""
    names = [tool.name for tool in registry.ALL_TOOLS]
    assert len(names) == len(set(names))
    assert {
        "search_contacts",
        "get_upcoming_todos",
        "get_contact_timeline",
        "get_stats",
        "create_task",
        "create_activity",
    } <= set(names)
    assert all(tool.risk in ("read", "write_queue") for tool in registry.ALL_TOOLS)


async def test_search_contacts_tool(db_session, make_user):
    """搜索工具：命中昵称，输出含展示名（agent 后续引用）。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")

    out = await _run_tool(db_session, demo, "search_contacts", query="老爸")
    assert "老爸" in out


async def test_search_contacts_respects_visibility(db_session, make_user):
    """搜索只出现在发起用户可读范围内（私密联系人不出现在家人搜索里）。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    await create_contact_for(demo, last_name="周", first_name="明", visibility="private")
    tong, _ = await create_family_user(family_id=demo.family_id, username="tong2")

    out = await _run_tool(db_session, tong, "search_contacts", query="周")
    assert "周明" not in out


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
    father = await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")
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
    await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")

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
    father = await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")
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

    mother = await create_contact_for(demo, last_name="李", first_name="秀", gender="female")
    uncle = await create_contact_for(demo, last_name="李", first_name="大勇", gender="male")
    me = await create_contact_for(demo, last_name="陈", first_name="小澄", gender="male")

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
