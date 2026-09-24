"""种子数据脚本：演示家庭/账号 + 关系类型字典 + 示例联系人（仅开发/演示用）。

用法：
    uv run python scripts/seed.py            # 空库时写入
    uv run python scripts/seed.py --force    # 清空业务数据后重写
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402

import app.models  # noqa: F401,E402  注册全部模型
from app.core.db import Base, get_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.modules.auth.models import Family, User  # noqa: E402
from app.modules.contacts.models import (  # noqa: E402
    Contact,
    ImportantDate,
)
from app.modules.funds.models import FundFlow  # noqa: E402
from app.modules.gifts.models import Gift, WishlistItem  # noqa: E402
from app.modules.graph.models import Relationship, RelationshipType  # noqa: E402
from app.modules.records.models import Activity, ActivityParticipant, Task  # noqa: E402

# 关系类型字典种子：（分组, 正向, 反向, 排序）
# 前三条为系统结构化类型（D15）：is_system + kind，边带 from_role/to_role 参与称谓推导
_RELATIONSHIP_TYPES = [
    ("family", "配偶", None, 0),
    ("family", "父母-子女", None, 0),
    ("family", "兄弟姐妹", None, 0),
    ("family", "丈夫", "妻子", 1),
    ("family", "父亲", "子女", 2),
    ("family", "母亲", "子女", 3),
    ("family", "儿子", "父母", 4),
    ("family", "女儿", "父母", 5),
    ("family", "哥哥", "弟弟/妹妹", 6),
    ("family", "姐姐", "弟弟/妹妹", 7),
    ("family", "爷爷", "孙辈", 8),
    ("family", "奶奶", "孙辈", 9),
    ("family", "外公", "孙辈", 10),
    ("family", "外婆", "孙辈", 11),
    ("family", "舅舅", "外甥/外甥女", 12),
    ("family", "姑姑", "侄子/侄女", 13),
    ("friend", "朋友", "朋友", 1),
    ("friend", "同学", "同学", 2),
    ("friend", "室友", "室友", 3),
    ("friend", "邻居", "邻居", 4),
    ("work", "同事", "同事", 1),
    ("work", "领导", "下属", 2),
    ("work", "下属", "领导", 3),
    ("work", "合作方", "合作方", 4),
    ("other", "师傅", "徒弟", 1),
    ("other", "医生", "患者", 2),
    ("other", "教练", "学员", 3),
]

DEMO_PASSWORD = "demo12345"


_SYSTEM_KINDS = {"配偶": "spouse", "父母-子女": "parent", "兄弟姐妹": "sibling"}


async def _seed_relationship_types(session) -> dict[tuple[str, str], int]:
    """写入关系类型字典（表空才写），返回 (分组, 正向标签) → id 的映射。

    前三种系统结构化类型带 is_system/kind（D15），其余为普通自定义类型。
    """
    existing = await session.scalar(select(func.count()).select_from(RelationshipType))
    if not existing:
        for group, name, reverse, order in _RELATIONSHIP_TYPES:
            session.add(
                RelationshipType(
                    group_name=group, name=name, reverse_name=reverse, sort_order=order,
                    is_system=name in _SYSTEM_KINDS, kind=_SYSTEM_KINDS.get(name),
                )
            )
        await session.flush()

    all_types = (await session.execute(select(RelationshipType))).scalars().all()
    return {(t.group_name, t.name): t.id for t in all_types}


async def _seed_demo_family(session, type_map: dict[tuple[str, str], int]) -> None:
    """写入演示家庭、成员与示例联系人。"""
    existing = await session.scalar(
        select(func.count()).select_from(User).where(User.username == "demo")
    )
    if existing:
        return

    family = Family(name="演示家庭")
    session.add(family)
    await session.flush()

    password_hash = hash_password(DEMO_PASSWORD)
    demo = User(
        family_id=family.id, username="demo", display_name="阿澄", password_hash=password_hash
    )
    wife = User(
        family_id=family.id, username="tong", display_name="小彤", password_hash=password_hash
    )
    session.add_all([demo, wife])
    await session.flush()

    # 直接联系人
    father = Contact(
        owner_user_id=demo.id, family_id=family.id, last_name="陈", first_name="建国",
        nickname="老爸", gender="male", visibility="family",
    )
    mother = Contact(
        owner_user_id=demo.id, family_id=family.id, last_name="陈", first_name="秀兰",
        nickname="老妈", gender="female", visibility="family",
    )
    colleague = Contact(
        owner_user_id=demo.id, family_id=family.id, last_name="张", first_name="伟",
        gender="male", organization="极星科技", visibility="family", bio="产品部同事，球友",
    )
    classmate = Contact(
        owner_user_id=wife.id, family_id=family.id, last_name="李", first_name="娜",
        gender="female", visibility="family", bio="大学室友",
    )
    private_friend = Contact(
        owner_user_id=demo.id, family_id=family.id, last_name="周", first_name="明",
        gender="male", visibility="private", bio="仅自己可见的示例",
    )
    # 边缘联系人（叶子）：张伟的妻子与儿子
    colleague_wife = Contact(
        owner_user_id=demo.id, family_id=family.id, tier="edge", last_name="王",
        first_name="芳", gender="female", visibility="family",
    )
    colleague_son = Contact(
        owner_user_id=demo.id, family_id=family.id, tier="edge", nickname="张小宝",
        gender="male", visibility="family",
    )
    # "我"：demo 账号绑定的联系人节点（D15 视角推导起点）
    me = Contact(
        owner_user_id=demo.id, family_id=family.id, last_name="陈", first_name="澄",
        nickname="阿澄", gender="male", visibility="family",
    )
    session.add_all(
        [father, mother, colleague, classmate, private_friend, colleague_wife, colleague_son, me]
    )
    await session.flush()

    # 账号绑定"我是谁"（D15）：demo→阿澄；小彤绑到李娜（家庭内以她视角演示岳家语义）
    demo.contact_id = me.id
    wife.contact_id = classmate.id

    # 重要日期：父亲公历生日 + 母亲农历三月初三生日（演示双历法）
    session.add_all([
        ImportantDate(
            contact_id=father.id, owner_user_id=demo.id, family_id=family.id,
            type="birthday", calendar="solar", date_solar=date(1958, 5, 12),
            reminder_lead_days=[7, 1],
        ),
        ImportantDate(
            contact_id=mother.id, owner_user_id=demo.id, family_id=family.id,
            type="birthday", calendar="lunar", lunar_month=3, lunar_day=3,
            reminder_lead_days=[7, 1],
        ),
    ])

    # 关系边（边可见性 = 两端可见性交集，查询期计算；含跨用户边）。
    # 系统类型（D15）：角色必填，语义 from 是 to 的 from_role / to 是 from 的 to_role
    spouse_type = type_map[("family", "配偶")]
    parent_type = type_map[("family", "父母-子女")]
    sibling_type = type_map[("family", "兄弟姐妹")]
    session.add_all([
        # 陈家：爸爸-妈妈夫妻，阿澄(我)与李娜是兄妹
        Relationship(
            from_contact_id=father.id, to_contact_id=mother.id,
            type_id=spouse_type, from_role="husband", to_role="wife",
            owner_user_id=demo.id, family_id=family.id,
        ),
        Relationship(
            from_contact_id=father.id, to_contact_id=me.id,
            type_id=parent_type, from_role="father", to_role="son",
            owner_user_id=demo.id, family_id=family.id,
        ),
        Relationship(
            from_contact_id=mother.id, to_contact_id=me.id,
            type_id=parent_type, from_role="mother", to_role="son",
            owner_user_id=demo.id, family_id=family.id,
        ),
        Relationship(
            from_contact_id=father.id, to_contact_id=classmate.id,
            type_id=parent_type, from_role="father", to_role="daughter",
            owner_user_id=demo.id, family_id=family.id,
        ),
        Relationship(
            from_contact_id=mother.id, to_contact_id=classmate.id,
            type_id=parent_type, from_role="mother", to_role="daughter",
            owner_user_id=demo.id, family_id=family.id,
        ),
        Relationship(
            from_contact_id=me.id, to_contact_id=classmate.id,
            type_id=sibling_type, from_role="elder_brother", to_role="younger_sister",
            owner_user_id=demo.id, family_id=family.id,
        ),
        # 张伟一家：夫妻 + 父子
        Relationship(
            from_contact_id=colleague.id, to_contact_id=colleague_wife.id,
            type_id=spouse_type, from_role="husband", to_role="wife",
            owner_user_id=demo.id, family_id=family.id,
        ),
        Relationship(
            from_contact_id=colleague.id, to_contact_id=colleague_son.id,
            type_id=parent_type, from_role="father", to_role="son",
            owner_user_id=demo.id, family_id=family.id,
        ),
        # 普通类型（无角色语义，不参与称谓推导）
        Relationship(
            from_contact_id=colleague.id, to_contact_id=classmate.id,
            type_id=type_map[("friend", "同学")], owner_user_id=wife.id, family_id=family.id,
        ),
    ])

    # ---- L3 生活与人情数据（日期相对 today，保证演示状态真实）----
    now = datetime.now(UTC)
    today = date.today()

    def days_from_now(days: int) -> datetime:
        """生成当前时刻偏移 N 天的时间（活动/任务时间字段用）。"""
        return now + timedelta(days=days)

    def days_from_today(days: int) -> date:
        """生成今天偏移 N 天的日期（礼物/资金日期字段用）。"""
        return today + timedelta(days=days)

    # 活动：一次近期家宴 + 一次球局 + 一次久远的同学聚会（演示"最近联系"统计口径）
    family_dinner = Activity(
        owner_user_id=demo.id, family_id=family.id,
        title="家庭聚餐", occurred_at=days_from_now(-3), location="老家",
        detail="爸妈掌勺，聊了国庆回家安排。",
    )
    ball_game = Activity(
        owner_user_id=demo.id, family_id=family.id,
        title="和张伟打球", occurred_at=days_from_now(-10), location="公司附近的球馆",
    )
    classmate_meetup = Activity(
        owner_user_id=wife.id, family_id=family.id,
        title="大学同学聚会", occurred_at=days_from_now(-75), location="市区火锅店",
        visibility="family",
    )
    # 未来活动：进入待办聚合（"准备进行的活动时间"来源演示）
    upcoming_visit = Activity(
        owner_user_id=demo.id, family_id=family.id,
        title="周末回老家看爸妈", occurred_at=days_from_now(4), location="老家",
    )
    session.add_all([family_dinner, ball_game, classmate_meetup, upcoming_visit])
    await session.flush()
    session.add_all([
        ActivityParticipant(activity_id=family_dinner.id, contact_id=father.id),
        ActivityParticipant(activity_id=family_dinner.id, contact_id=mother.id),
        ActivityParticipant(activity_id=ball_game.id, contact_id=colleague.id),
        ActivityParticipant(activity_id=classmate_meetup.id, contact_id=classmate.id),
        ActivityParticipant(activity_id=upcoming_visit.id, contact_id=father.id),
        ActivityParticipant(activity_id=upcoming_visit.id, contact_id=mother.id),
    ])

    # 任务：一条临近截止（演示"已过期/临近"），一条无期限
    session.add_all([
        Task(
            owner_user_id=demo.id, family_id=family.id,
            title="给老爸准备生日礼物", due_at=days_from_now(3), contact_id=father.id,
        ),
        Task(
            owner_user_id=demo.id, family_id=family.id,
            title="整理通讯录照片", due_at=days_from_now(-2),
        ),
        Task(
            owner_user_id=wife.id, family_id=family.id,
            title="约李娜喝下午茶", contact_id=classmate.id, visibility="family",
        ),
    ])

    # 礼物往来：送出/收到各一条以上，金额与场合可选演示
    session.add_all([
        Gift(
            owner_user_id=demo.id, family_id=family.id, contact_id=mother.id,
            direction="given", title="按摩仪", occasion="生日", amount="599.00",
            given_at=days_from_today(-20), description="肩颈按摩仪，**妈说很舒服**。",
        ),
        Gift(
            owner_user_id=demo.id, family_id=family.id, contact_id=colleague.id,
            direction="given", title="明前龙井", occasion="帮忙搬家", amount="200.00",
            given_at=days_from_today(-9),
        ),
        Gift(
            owner_user_id=wife.id, family_id=family.id, contact_id=classmate.id,
            direction="received", title="羊绒围巾", occasion="生日", amount="300.00",
            given_at=days_from_today(-15), visibility="family",
        ),
    ])

    # 愿望清单：一条想送（带目标日期），一条已购买
    session.add_all([
        WishlistItem(
            owner_user_id=demo.id, family_id=family.id, contact_id=father.id,
            title="血压仪", amount="399.00", status="open",
            target_date=days_from_today(7), link="https://example.com/bp-monitor",
        ),
        WishlistItem(
            owner_user_id=demo.id, family_id=family.id, contact_id=colleague_wife.id,
            title="香薰蜡烛", amount="129.00", status="purchased",
        ),
    ])

    # 资金往来：一笔未结清借款（临近应还日）+ 一笔已结清 + 一笔礼金（不涉及结清）
    session.add_all([
        FundFlow(
            owner_user_id=demo.id, family_id=family.id, contact_id=colleague.id,
            direction="out", category="loan", amount="2000.00",
            occurred_at=days_from_today(-30), due_at=days_from_today(5),
            status="pending", description="他说换车垫一下，月内还。",
        ),
        FundFlow(
            owner_user_id=demo.id, family_id=family.id, contact_id=classmate.id,
            direction="in", category="repayment", amount="1000.00",
            occurred_at=days_from_today(-12), due_at=days_from_today(-12),
            status="settled", settled_at=days_from_today(-12),
        ),
        FundFlow(
            owner_user_id=demo.id, family_id=family.id, contact_id=father.id,
            direction="out", category="gift_money", amount="800.00",
            occurred_at=days_from_today(-40), description="表弟婚礼随礼。",
        ),
    ])


async def seed(force: bool) -> None:
    """执行种子流程；force 时先清空业务表。"""
    factory = get_session_factory()
    async with factory() as session:
        if force:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))
        type_map = await _seed_relationship_types(session)
        await _seed_demo_family(session, type_map)
        await session.commit()
        user_count = await session.scalar(select(func.count()).select_from(User))
        contact_count = await session.scalar(select(func.count()).select_from(Contact))
        activity_count = await session.scalar(select(func.count()).select_from(Activity))
        gift_count = await session.scalar(select(func.count()).select_from(Gift))
        fund_count = await session.scalar(select(func.count()).select_from(FundFlow))
        print(
            f"种子完成：用户 {user_count}，联系人 {contact_count}，"
            f"活动 {activity_count}，礼物 {gift_count}，资金 {fund_count}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="写入演示种子数据")
    parser.add_argument("--force", action="store_true", help="清空业务数据后重写")
    args = parser.parse_args()
    asyncio.run(seed(force=args.force))
