"""graph 模块测试：关系类型字典、关系边 CRUD（可见性交集/反向推导）、N 度图数据。"""

import pytest

from tests.factories import (
    create_contact_for,
    create_family_user,
)

pytestmark = pytest.mark.asyncio


async def _make_type(
    client, headers, name: str, reverse: str | None = None, group: str = "family"
) -> int:
    """造一个关系类型，返回 id。"""
    resp = await client.post(
        "/api/v1/graph/relationship-types",
        json={"group_name": group, "name": name, "reverse_name": reverse},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def test_relationship_type_create_and_dedup(client, make_user, login_headers):
    """字典：可新增自定义类型；同名重复 → 409。"""
    await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")

    listed = (await client.get("/api/v1/graph/relationship-types", headers=headers)).json()
    assert listed == []  # 测试库无种子，从空开始

    first = await _make_type(client, headers, "师傅", "徒弟", group="other")
    again = await client.post(
        "/api/v1/graph/relationship-types",
        json={"group_name": "other", "name": "师傅", "reverse_name": None},
        headers=headers,
    )
    assert again.status_code == 409

    listed = (await client.get("/api/v1/graph/relationship-types", headers=headers)).json()
    assert [t["id"] for t in listed] == [first]


async def test_create_relationship_validations(client, make_user, login_headers):
    """建边校验：自环/类型不存在/包含不可读联系人 → 422，不落库。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    other, _ = await make_user(username="other")
    hidden = await create_contact_for(other, last_name="私", first_name="人", visibility="private")
    father = await create_contact_for(demo, last_name="陈", first_name="建国")
    headers = await login_headers("demo", "demo12345")
    type_id = await _make_type(client, headers, "父亲", "子女")

    self_loop = await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": father.id, "to_contact_id": father.id, "type_id": type_id},
        headers=headers,
    )
    assert self_loop.status_code == 422

    missing_type = await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": father.id, "to_contact_id": hidden.id, "type_id": 99999},
        headers=headers,
    )
    assert missing_type.status_code == 422

    unreadable_end = await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": father.id, "to_contact_id": hidden.id, "type_id": type_id},
        headers=headers,
    )
    assert unreadable_end.status_code == 422


async def test_relationship_reverse_direction_query(client, make_user, login_headers):
    """反向推导：A 是 B 的丈夫；从 B 视角查询应得到反向标签"妻子"。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")
    mother = await create_contact_for(demo, last_name="陈", first_name="秀兰", nickname="老妈")
    headers = await login_headers("demo", "demo12345")
    husband_type = await _make_type(client, headers, "丈夫", "妻子")

    created = await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": father.id, "to_contact_id": mother.id, "type_id": husband_type},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text

    from_father = (
        await client.get(f"/api/v1/graph/relationships?contact_id={father.id}", headers=headers)
    ).json()
    assert len(from_father) == 1
    assert from_father[0]["direction"] == "out"
    assert from_father[0]["type_label"] == "丈夫"
    assert from_father[0]["other_contact_name"] == "老妈"

    from_mother = (
        await client.get(f"/api/v1/graph/relationships?contact_id={mother.id}", headers=headers)
    ).json()
    assert len(from_mother) == 1
    assert from_mother[0]["direction"] == "in"
    assert from_mother[0]["type_label"] == "妻子"
    assert from_mother[0]["other_contact_name"] == "老爸"


async def test_relationship_duplicate_edge_rejected(client, make_user, login_headers):
    """同一对联系人 + 同一类型的边不可重复创建 → 409。"""
    demo, _ = await make_user(username="demo")
    a = await create_contact_for(demo, last_name="张", first_name="伟")
    b = await create_contact_for(demo, last_name="王", first_name="芳")
    headers = await login_headers("demo", "demo12345")
    type_id = await _make_type(client, headers, "同事", None, group="work")

    payload = {"from_contact_id": a.id, "to_contact_id": b.id, "type_id": type_id}
    await client.post("/api/v1/graph/relationships", json=payload, headers=headers)
    again = await client.post("/api/v1/graph/relationships", json=payload, headers=headers)
    assert again.status_code == 409


async def test_relationship_visibility_intersection(client, make_user, login_headers):
    """可见性交集：一端是私密联系人时，家庭成员看不到这条边。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    private_friend = await create_contact_for(
        demo, last_name="周", first_name="明", visibility="private"
    )
    father = await create_contact_for(demo, last_name="陈", first_name="建国", visibility="family")
    headers = await login_headers("demo", "demo12345")
    type_id = await _make_type(client, headers, "朋友", "朋友", group="friend")

    await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": private_friend.id, "to_contact_id": father.id, "type_id": type_id},
        headers=headers,
    )

    mine = (
        await client.get(f"/api/v1/graph/relationships?contact_id={father.id}", headers=headers)
    ).json()
    assert len(mine) == 1

    tong_headers = await login_headers("tong", "demo12345")
    theirs = (
        await client.get(
            f"/api/v1/graph/relationships?contact_id={father.id}", headers=tong_headers
        )
    ).json()
    assert theirs == []


async def test_relationship_delete_permissions(client, make_user, login_headers):
    """删边仅所有者：家人 403，所有者 204；不可见的边对家人按 404。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    a = await create_contact_for(demo, last_name="张", first_name="伟")
    b = await create_contact_for(demo, last_name="王", first_name="芳")
    headers = await login_headers("demo", "demo12345")
    type_id = await _make_type(client, headers, "同学", "同学", group="friend")

    edge = await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": a.id, "to_contact_id": b.id, "type_id": type_id},
        headers=headers,
    )
    edge_id = edge.json()["id"]
    tong_headers = await login_headers("tong", "demo12345")

    forbidden = await client.delete(f"/api/v1/graph/relationships/{edge_id}", headers=tong_headers)
    assert forbidden.status_code == 403

    deleted = await client.delete(f"/api/v1/graph/relationships/{edge_id}", headers=headers)
    assert deleted.status_code == 204


async def test_graph_data_center_expansion(client, make_user, login_headers):
    """N 度展开：以 A 为中心，depth=1 只有直接关系，depth=2 才到三度节点。"""
    demo, _ = await make_user(username="demo")
    a = await create_contact_for(demo, last_name="陈", first_name="建国")
    b = await create_contact_for(demo, last_name="陈", first_name="秀兰")
    c = await create_contact_for(demo, last_name="王", first_name="芳")
    headers = await login_headers("demo", "demo12345")
    husband = await _make_type(client, headers, "丈夫", "妻子")
    wife_side = await _make_type(client, headers, "母亲", "子女")

    await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": a.id, "to_contact_id": b.id, "type_id": husband},
        headers=headers,
    )
    await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": b.id, "to_contact_id": c.id, "type_id": wife_side},
        headers=headers,
    )

    one_degree = (
        await client.get(f"/api/v1/graph/data?center_id={a.id}&depth=1", headers=headers)
    ).json()
    assert {node["id"] for node in one_degree["nodes"]} == {a.id, b.id}
    assert len(one_degree["links"]) == 1

    two_degree = (
        await client.get(f"/api/v1/graph/data?center_id={a.id}&depth=2", headers=headers)
    ).json()
    assert {node["id"] for node in two_degree["nodes"]} == {a.id, b.id, c.id}
    assert len(two_degree["links"]) == 2
    node_names = {node["id"]: node["name"] for node in two_degree["nodes"]}
    assert node_names[a.id] == "陈建国"


async def test_graph_data_visibility_filtering(client, make_user, login_headers):
    """全图数据按可读范围过滤：家人视角不含私密联系人及其边。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    private_friend = await create_contact_for(
        demo, last_name="周", first_name="明", visibility="private"
    )
    father = await create_contact_for(demo, last_name="陈", first_name="建国", visibility="family")
    headers = await login_headers("demo", "demo12345")
    type_id = await _make_type(client, headers, "朋友", "朋友", group="friend")

    await client.post(
        "/api/v1/graph/relationships",
        json={"from_contact_id": private_friend.id, "to_contact_id": father.id, "type_id": type_id},
        headers=headers,
    )

    mine = (await client.get("/api/v1/graph/data", headers=headers)).json()
    assert {node["id"] for node in mine["nodes"]} == {private_friend.id, father.id}
    assert len(mine["links"]) == 1

    tong_headers = await login_headers("tong", "demo12345")
    theirs = (await client.get("/api/v1/graph/data", headers=tong_headers)).json()
    assert {node["id"] for node in theirs["nodes"]} == {father.id}
    assert theirs["links"] == []
