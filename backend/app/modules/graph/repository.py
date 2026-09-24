"""graph 模块数据访问层：关系字典/关系边/图数据的查询拼装（含只读 JOIN contacts）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.models import Contact
from app.modules.graph.models import Relationship, RelationshipType
from app.services.permission import readable_condition


async def list_relationship_types(db: AsyncSession) -> list[RelationshipType]:
    """全部关系类型（组内按 sort_order、组间按固定顺序由 Python 端稳定化）。"""
    stmt = select(RelationshipType).order_by(
        RelationshipType.group_name, RelationshipType.sort_order, RelationshipType.id
    )
    return list((await db.execute(stmt)).scalars().all())


async def find_type_by_name(db: AsyncSession, name: str) -> RelationshipType | None:
    """按正向标签取类型（字典去重判定用）。"""
    stmt = select(RelationshipType).where(RelationshipType.name == name)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_relationship_type(db: AsyncSession, type_id: int) -> RelationshipType | None:
    """按 id 取关系类型。"""
    return await db.get(RelationshipType, type_id)


async def create_relationship_type(
    db: AsyncSession, *, group_name: str, name: str, reverse_name: str | None
) -> RelationshipType:
    """写入自定义关系类型。"""
    relationship_type = RelationshipType(
        group_name=group_name, name=name, reverse_name=reverse_name, sort_order=99
    )
    db.add(relationship_type)
    await db.flush()
    return relationship_type


async def find_existing_edge(
    db: AsyncSession, *, from_contact_id: int, to_contact_id: int, type_id: int
) -> Relationship | None:
    """按 (from, to, type) 查重（唯一约束的前置友好检查）。"""
    stmt = select(Relationship).where(
        Relationship.from_contact_id == from_contact_id,
        Relationship.to_contact_id == to_contact_id,
        Relationship.type_id == type_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_edge(
    db: AsyncSession,
    *,
    owner_user_id: int,
    family_id: int,
    from_contact_id: int,
    to_contact_id: int,
    type_id: int,
    from_role: str | None,
    to_role: str | None,
    status: str,
    note: str | None,
) -> Relationship:
    """写入关系边（调用方负责全部业务校验，含角色值域）。"""
    edge = Relationship(
        owner_user_id=owner_user_id,
        family_id=family_id,
        from_contact_id=from_contact_id,
        to_contact_id=to_contact_id,
        type_id=type_id,
        from_role=from_role,
        to_role=to_role,
        status=status,
        note=note,
    )
    db.add(edge)
    await db.flush()
    return edge


async def find_relationships_of_contact(
    db: AsyncSession, user, contact_id: int
) -> list[tuple[Relationship, RelationshipType, Contact, str]]:
    """某联系人的全部关系边（可见性 = 两端联系人各自可读的交集）。

    返回 (边, 类型, 对方联系人, 方向)；方向 out=视角人物是主体，in=客体。
    """
    stmt = (
        select(Relationship, RelationshipType)
        .join(RelationshipType, RelationshipType.id == Relationship.type_id)
        .where(
            (Relationship.from_contact_id == contact_id)
            | (Relationship.to_contact_id == contact_id)
        )
    )
    rows = list((await db.execute(stmt)).all())

    # 两端联系人可读性交集：逐行校验两端（数据量小，避免复杂 join 拼装）
    from app.modules.contacts.repository import find_readable_contacts_by_ids

    result: list[tuple[Relationship, RelationshipType, Contact, str]] = []
    for edge, relationship_type in rows:
        both = await find_readable_contacts_by_ids(
            db, user, [edge.from_contact_id, edge.to_contact_id]
        )
        if edge.from_contact_id not in both or edge.to_contact_id not in both:
            continue
        other_id = (
            edge.to_contact_id if edge.from_contact_id == contact_id else edge.from_contact_id
        )
        direction = "out" if edge.from_contact_id == contact_id else "in"
        result.append((edge, relationship_type, both[other_id], direction))
    return result


async def get_readable_edge(
    db: AsyncSession, user, edge_id: int
) -> Relationship | None:
    """按 id 取当前用户可见的关系边（两端可读交集）；不可见一律 None。"""
    stmt = select(Relationship).where(Relationship.id == edge_id)
    edge = (await db.execute(stmt)).scalar_one_or_none()
    if edge is None:
        return None

    from app.modules.contacts.repository import find_readable_contacts_by_ids

    both = await find_readable_contacts_by_ids(
        db, user, [edge.from_contact_id, edge.to_contact_id]
    )
    if edge.from_contact_id not in both or edge.to_contact_id not in both:
        return None
    return edge


async def list_reachable_ids(
    db: AsyncSession, *, center_id: int, depth: int
) -> set[int]:
    """递归 CTE：从中心联系人沿关系边（双向）扩展 depth 度内的节点 id 集合。

    UNION（去重）天然防环；可读性过滤在拿到集合后由调用方按联系人范围收口。
    """
    from sqlalchemy import text

    sql = text(
        """
        WITH RECURSIVE reached(id, depth) AS (
            SELECT CAST(:center_id AS BIGINT), 0
            UNION
            SELECT CASE WHEN r.from_contact_id = w.id
                        THEN r.to_contact_id ELSE r.from_contact_id END,
                   w.depth + 1
            FROM relationships r
            JOIN reached w ON r.from_contact_id = w.id OR r.to_contact_id = w.id
            WHERE w.depth < :depth
        )
        SELECT id FROM reached
        """
    )
    rows = await db.execute(sql, {"center_id": center_id, "depth": depth})
    return {row[0] for row in rows}


async def find_readable_nodes_by_ids(
    db: AsyncSession, user, contact_ids: set[int]
) -> list[Contact]:
    """从 id 集合中筛出可读且在册的联系人（图节点）。"""
    if not contact_ids:
        return []
    stmt = (
        select(Contact)
        .where(
            Contact.id.in_(contact_ids),
            Contact.status == "active",
            readable_condition(Contact, user),
        )
        .order_by(Contact.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def find_all_readable_nodes(db: AsyncSession, user) -> list[Contact]:
    """全部可读且在册的联系人（全图模式节点集）。"""
    stmt = (
        select(Contact)
        .where(Contact.status == "active", readable_condition(Contact, user))
        .order_by(Contact.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def find_readable_edges_among(
    db: AsyncSession, user, contact_ids: set[int]
) -> list[tuple[Relationship, RelationshipType]]:
    """取两端都在给定集合内的可读关系边（图链接）。"""
    if not contact_ids:
        return []
    stmt = (
        select(Relationship, RelationshipType)
        .join(RelationshipType, RelationshipType.id == Relationship.type_id)
        .where(
            Relationship.from_contact_id.in_(contact_ids),
            Relationship.to_contact_id.in_(contact_ids),
        )
    )
    rows = list((await db.execute(stmt)).all())

    from app.modules.contacts.repository import find_readable_contacts_by_ids

    result: list[tuple[Relationship, RelationshipType]] = []
    for edge, relationship_type in rows:
        both = await find_readable_contacts_by_ids(
            db, user, [edge.from_contact_id, edge.to_contact_id]
        )
        if edge.from_contact_id not in both or edge.to_contact_id not in both:
            continue
        result.append((edge, relationship_type))
    return result
