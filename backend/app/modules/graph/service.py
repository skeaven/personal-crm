"""graph 模块服务层：关系字典/关系边业务规则与图数据组装。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.contacts import repository as contact_repo
from app.modules.contacts.models import Contact
from app.modules.graph import kinship
from app.modules.graph import repository as graph_repo
from app.modules.graph.models import RelationshipType
from app.modules.graph.schemas import (
    GraphDataOut,
    GraphLinkOut,
    GraphNodeOut,
    KinshipOut,
    KinshipStepOut,
    RelationshipCreate,
    RelationshipOut,
    RelationshipTypeCreate,
    RelationshipTypeOut,
)
from app.services.permission import ensure_can_write


async def list_relationship_types(db: AsyncSession) -> list[RelationshipTypeOut]:
    """关系类型字典（全局共享，家庭成员皆可读）。"""
    types = await graph_repo.list_relationship_types(db)
    return [RelationshipTypeOut.model_validate(item) for item in types]


async def create_relationship_type(
    db: AsyncSession, user: User, data: RelationshipTypeCreate
) -> RelationshipTypeOut:
    """新增自定义关系类型：正向标签全局唯一（重复 409）。"""
    existing = await graph_repo.find_type_by_name(db, data.name)
    if existing is not None:
        raise ConflictError(f"关系类型「{data.name}」已存在")
    created = await graph_repo.create_relationship_type(
        db,
        group_name=data.group_name,
        name=data.name,
        reverse_name=data.reverse_name or None,
    )
    return RelationshipTypeOut.model_validate(created)


def _type_label(relationship_type: RelationshipType, direction: str) -> str:
    """按视角方向取标签：客体视角用反向标签，对称关系（无反向）回落正向。"""
    if direction == "in" and relationship_type.reverse_name:
        return relationship_type.reverse_name
    return relationship_type.name


async def create_relationship(
    db: AsyncSession, user: User, data: RelationshipCreate
) -> RelationshipOut:
    """创建关系边（跨用户边允许，归属创建者）：两端须对创建者可读，重复边 409。"""
    readable = await contact_repo.find_readable_contacts_by_ids(
        db, user, [data.from_contact_id, data.to_contact_id]
    )
    missing = {data.from_contact_id, data.to_contact_id} - set(readable)
    if missing:
        raise ValidationError("关系两端存在不可见的联系人")
    relationship_type = await graph_repo.get_relationship_type(db, data.type_id)
    if relationship_type is None:
        raise ValidationError("关系类型不存在")
    from_role, to_role = _validated_roles(relationship_type, data.from_role, data.to_role)
    if data.status not in ("active", "former"):
        raise ValidationError("status 必须是 active 或 former")
    if await graph_repo.find_existing_edge(
        db,
        from_contact_id=data.from_contact_id,
        to_contact_id=data.to_contact_id,
        type_id=data.type_id,
    ):
        raise ConflictError("这条关系已经存在")

    edge = await graph_repo.create_edge(
        db,
        owner_user_id=user.id,
        family_id=user.family_id,
        from_contact_id=data.from_contact_id,
        to_contact_id=data.to_contact_id,
        type_id=data.type_id,
        from_role=from_role,
        to_role=to_role,
        status=data.status,
        note=data.note,
    )
    # 建边后以主体视角返回（direction=out）
    return _to_relationship_out(
        edge, readable[data.to_contact_id], readable, "out", relationship_type=relationship_type
    )


def _validated_roles(
    relationship_type: RelationshipType, from_role: str | None, to_role: str | None
) -> tuple[str | None, str | None]:
    """按类型类别校验角色值域（D15）：系统类型必填且在值域内；自定义类型忽略角色。"""
    kind = relationship_type.kind
    if not relationship_type.is_system or kind not in kinship.ROLE_DOMAINS:
        if from_role or to_role:
            raise ValidationError("自定义关系类型不支持角色字段")
        return None, None
    domain = kinship.ROLE_DOMAINS[kind]
    if from_role not in domain["from"] or to_role not in domain["to"]:
        hint = f"{domain['from']} / {domain['to']}"
        raise ValidationError(f"角色取值须在 {kind} 类型的值域内：{hint}")
    return from_role, to_role


def _to_relationship_out(
    edge,
    other: Contact,
    contacts_by_id: dict[int, Contact],
    direction: str,
    relationship_type: RelationshipType | None = None,
    owner_display_name: str = "",
) -> RelationshipOut:
    """组装视角化关系输出：称谓句式（kinship_label）优先，role 缺失退回标签句式。"""
    label = _type_label(relationship_type, direction) if relationship_type else ""
    kinship_label = None
    if relationship_type and relationship_type.is_system and relationship_type.kind:
        # 视角人物在 from 端 → 目标角色是 to_role；在 to 端 → from_role
        target_role = edge.to_role if direction == "out" else edge.from_role
        if target_role:
            kinship_label = kinship.kinship_title([(relationship_type.kind, target_role)])
    return RelationshipOut(
        id=edge.id,
        direction=direction,
        other_contact_id=other.id,
        other_contact_name=other.display_name,
        other_tier=other.tier,
        type_id=edge.type_id,
        type_label=label,
        type_name=relationship_type.name if relationship_type else "",
        kind=relationship_type.kind if relationship_type else None,
        kinship_label=kinship_label,
        status=edge.status,
        note=edge.note,
        owner_user_id=edge.owner_user_id,
        owner_display_name=owner_display_name,
        created_at=edge.created_at,
    )


async def list_relationships_of_contact(
    db: AsyncSession, user: User, contact_id: int
) -> list[RelationshipOut]:
    """某联系人的关系列表（双向，方向归一）；中心联系人不可见按 404。"""
    center = await contact_repo.get_readable_contact(db, user, contact_id)
    if center is None:
        raise NotFoundError("联系人不存在")

    outputs: list[RelationshipOut] = []
    for edge, relationship_type, other, direction in await graph_repo.find_relationships_of_contact(
        db, user, contact_id
    ):
        contacts_by_id = {contact.id: contact for contact in [center, other]}
        owner = await db.get(User, edge.owner_user_id)
        outputs.append(
            _to_relationship_out(
                edge,
                other,
                contacts_by_id,
                direction,
                relationship_type=relationship_type,
                owner_display_name=owner.display_name if owner else "未知",
            )
        )
    return outputs


async def delete_relationship(db: AsyncSession, user: User, edge_id: int) -> None:
    """删除关系边（仅所有者）；对不可见者按 404，可见但非所有者 403。"""
    edge = await graph_repo.get_readable_edge(db, user, edge_id)
    if edge is None:
        raise NotFoundError("关系不存在")
    ensure_can_write(user, edge)
    await db.delete(edge)
    await db.flush()


async def get_graph_data(
    db: AsyncSession, user: User, *, center_id: int | None, depth: int
) -> GraphDataOut:
    """组装图数据：全图（无中心）或中心 N 度展开；节点/边均按可读范围过滤。"""
    if center_id is not None:
        center = await contact_repo.get_readable_contact(db, user, center_id)
        if center is None:
            raise NotFoundError("联系人不存在")
        reachable = await graph_repo.list_reachable_ids(db, center_id=center_id, depth=depth)
        reachable.add(center_id)
    else:
        reachable = None  # None 表示全图

    if reachable is None:
        nodes = await graph_repo.find_all_readable_nodes(db, user)
    else:
        nodes = await graph_repo.find_readable_nodes_by_ids(db, user, reachable)
    node_ids = {node.id for node in nodes}

    links: list[GraphLinkOut] = []
    for edge, relationship_type in await graph_repo.find_readable_edges_among(db, user, node_ids):
        links.append(
            GraphLinkOut(
                id=edge.id,
                source=edge.from_contact_id,
                target=edge.to_contact_id,
                label=relationship_type.name,
            )
        )

    return GraphDataOut(
        nodes=[
            GraphNodeOut(id=node.id, name=node.display_name, tier=node.tier) for node in nodes
        ],
        links=links,
    )


async def kinship_of(db: AsyncSession, user: User, contact_id: int) -> KinshipOut:
    """从"我"（user.contact_id）到目标的称谓推导（D15）。

    家庭量级（数百节点）直接全图 BFS：跳数最短先达；同跳数多条路径取
    称谓规则可解释的第一条，全不可解释则报路径但 title 为空。跳过 former 边。
    """
    if user.contact_id is None:
        raise ValidationError("当前账号还没有绑定「我是谁」，请先在设置里选择自己的联系人")
    target = await contact_repo.get_readable_contact(db, user, contact_id)
    if target is None:
        raise NotFoundError("联系人不存在")

    nodes = await graph_repo.find_all_readable_nodes(db, user)
    contacts_by_id = {node.id: node for node in nodes}
    if user.contact_id not in contacts_by_id or contact_id not in contacts_by_id:
        return KinshipOut(found=False)
    if contact_id == user.contact_id:
        return KinshipOut(found=True, title="我自己", generation_diff=0, path=[])

    edges = await graph_repo.find_readable_edges_among(db, user, set(contacts_by_id))
    adjacency: dict[int, list[tuple[int, str | None, str | None]]] = {}
    for edge, relationship_type in edges:
        if edge.status != "active" or not relationship_type or not relationship_type.is_system:
            continue
        adjacency.setdefault(edge.from_contact_id, []).append(
            (edge.to_contact_id, relationship_type.kind, edge.to_role)
        )
        adjacency.setdefault(edge.to_contact_id, []).append(
            (edge.from_contact_id, relationship_type.kind, edge.from_role)
        )

    # BFS：首达即最短跳数；同层多路取第一条可解释称谓
    from collections import deque

    queue: deque[tuple[int, list[KinshipStepOut], list[tuple[str, str]]]] = deque()
    queue.append((user.contact_id, [], []))
    visited = {user.contact_id}
    best: tuple[list[KinshipStepOut], list[tuple[str, str]]] | None = None
    while queue:
        current_id, path, role_path = queue.popleft()
        if current_id == contact_id:
            best = (path, role_path)
            break
        for next_id, kind, role in adjacency.get(current_id, []):
            if next_id in visited or not kind or not role:
                continue
            visited.add(next_id)
            next_contact = contacts_by_id[next_id]
            queue.append((
                next_id,
                path + [KinshipStepOut(
                    contact_id=next_id, name=next_contact.display_name, kind=kind, role=role
                )],
                role_path + [(kind, role)],
            ))
    if best is None:
        return KinshipOut(found=False)

    path, role_path = best
    return KinshipOut(
        found=True,
        title=kinship.kinship_title(role_path),
        generation_diff=kinship.generation_diff(role_path),
        path=path,
    )
