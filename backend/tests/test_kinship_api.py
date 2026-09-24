"""kinship 视角推导 API 测试（D15）：系统类型建边校验、角色句式、路径称谓。"""

import pytest

from tests.factories import create_contact_for

pytestmark = pytest.mark.asyncio

# 系统类型在测试库由 create_all 建表但无种子：用 API 前先造（service 层直接造行）
async def _make_system_types(client, headers) -> dict[str, int]:
    """直接经 DB 造三条系统类型（API 不开放创建系统类型），返回 kind → id。"""
    from sqlalchemy import select

    from app.core.db import get_session_factory
    from app.modules.graph.models import RelationshipType

    factory = get_session_factory()
    async with factory() as session:
        kinds = {"spouse": "配偶", "parent": "父母-子女", "sibling": "兄弟姐妹"}
        for kind, name in kinds.items():
            session.add(RelationshipType(
                group_name="family", name=name, is_system=True, kind=kind
            ))
        await session.commit()
        rows = (await session.execute(
            select(RelationshipType).where(RelationshipType.is_system)
        )).scalars().all()
        return {row.kind: row.id for row in rows}


async def _create_edge(client, headers, **payload) -> dict:
    resp = await client.post(
        "/api/v1/graph/relationships", json=payload, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def test_system_edge_requires_valid_roles(client, make_user, login_headers):
    """系统类型建边：角色缺失/值域外 → 422；合法角色成功且返回称谓句式。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, last_name="陈", first_name="建国", gender="male")
    son = await create_contact_for(demo, last_name="陈", first_name="小澄", gender="male")
    headers = await login_headers("demo", "demo12345")
    types = await _make_system_types(client, headers)

    missing = await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": father.id, "to_contact_id": son.id, "type_id": types["parent"]},
        headers=headers,
    )
    assert missing.status_code == 422

    bad_role = await client.post(
        "/api/v1/graph/relationships",
        json={
            "from_contact_id": father.id, "to_contact_id": son.id, "type_id": types["parent"],
            "from_role": "uncle", "to_role": "son",
        },
        headers=headers,
    )
    assert bad_role.status_code == 422

    ok = _created = await client.post(
        "/api/v1/graph/relationships",
        json={
            "from_contact_id": father.id, "to_contact_id": son.id, "type_id": types["parent"],
            "from_role": "father", "to_role": "son",
        },
        headers=headers,
    )
    assert _created.status_code == 201 or ok.status_code == 200
    body = _created.json()
    assert body["kind"] == "parent"
    assert body["kinship_label"] == "儿子"  # 建边视角是主体（父）：target=son 的单跳称谓


async def test_relationship_list_uses_kinship_label(client, make_user, login_headers):
    """关系列表：从中心联系人视角输出称谓（爸爸/哥哥），role 空退回标签句式。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, last_name="陈", first_name="建国", gender="male")
    me = await create_contact_for(demo, last_name="陈", first_name="小澄", gender="male")
    headers = await login_headers("demo", "demo12345")
    types = await _make_system_types(client, headers)

    await _create_edge(
        client, headers, from_contact_id=father.id, to_contact_id=me.id,
        type_id=types["parent"], from_role="father", to_role="son",
    )
    # 旧式边（自定义类型，无角色）→ 兼容句式
    custom_type = await _make_type_plain(client, headers)
    colleague = await create_contact_for(demo, last_name="王", first_name="同事")
    await _create_edge(
        client, headers, from_contact_id=me.id, to_contact_id=colleague.id,
        type_id=custom_type,
    )

    listed = (
        await client.get(f"/api/v1/graph/relationships?contact_id={me.id}", headers=headers)
    ).json()
    by_name = {item["other_contact_name"]: item for item in listed}
    assert by_name["陈建国"]["kinship_label"] == "爸爸"
    assert by_name["王同事"]["kinship_label"] is None
    assert by_name["王同事"]["type_label"]  # 兼容句式仍有标签


async def test_kinship_path_two_hops(client, make_user, login_headers):
    """两跳推导：我→妈妈→(妈妈的哥哥)=舅舅；路径含角色序列与辈分差。"""
    demo, _ = await make_user(username="demo")
    mother = await create_contact_for(demo, last_name="李", first_name="秀", gender="female")
    uncle = await create_contact_for(demo, last_name="李", first_name="大勇", gender="male")
    me = await create_contact_for(demo, last_name="陈", first_name="小澄", gender="male")
    headers = await login_headers("demo", "demo12345")
    types = await _make_system_types(client, headers)

    await client.put(
        "/api/v1/auth/me", json={"contact_id": me.id}, headers=headers
    )
    await _create_edge(
        client, headers, from_contact_id=mother.id, to_contact_id=me.id,
        type_id=types["parent"], from_role="mother", to_role="son",
    )
    await _create_edge(
        client, headers, from_contact_id=uncle.id, to_contact_id=mother.id,
        type_id=types["sibling"], from_role="elder_brother", to_role="younger_sister",
    )

    resp = await client.get(f"/api/v1/graph/kinship?contact_id={uncle.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["found"] is True
    assert body["title"] == "舅舅"
    assert body["generation_diff"] == 1
    assert [step["name"] for step in body["path"]] == ["李秀", "李大勇"]


async def test_kinship_requires_binding(client, make_user, login_headers):
    """未绑定"我"：称谓查询返回 400 提示绑定。"""
    demo, _ = await make_user(username="demo")
    other = await create_contact_for(demo, last_name="某", first_name="人")
    headers = await login_headers("demo", "demo12345")
    resp = await client.get(f"/api/v1/graph/kinship?contact_id={other.id}", headers=headers)
    assert resp.status_code == 422


async def _make_type_plain(client, headers) -> int:
    """造普通自定义类型（无 kind），返回 id。"""
    resp = await client.post(
        "/api/v1/graph/relationship-types",
        json={"group_name": "friend", "name": "同事", "reverse_name": "同事"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]
