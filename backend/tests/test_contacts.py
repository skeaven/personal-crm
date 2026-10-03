"""联系人模块测试：CRUD、双层模型、权限隔离、同名防线、升级与归档、详情区块。"""

import pytest

from tests.factories import (
    create_contact_for,
    create_date_for,
    create_family_user,
    login_as,
)


@pytest.fixture
async def family_users():
    """同一家庭的一对成员：阿澄（所有者）与小彤（家庭只读成员）。"""
    owner, _ = await create_family_user(username="demo", display_name="阿澄")
    member, _ = await create_family_user(
        username="tong", display_name="小彤", family_id=owner.family_id
    )
    return owner, member


async def test_detail_includes_dates_block(client, family_users):
    """详情接口返回重要日期区块（详情页核心枢纽的第一个增量区块）。"""
    from datetime import date

    owner, member = family_users
    contact = await create_contact_for(owner, name="陈建国", nickname="老爸")
    await create_date_for(
        owner,
        contact_id=contact.id,
        type="birthday",
        calendar="solar",
        date_solar=date(1958, 5, 12),
        reminder_lead_days=[7, 1],
    )

    owner_headers = await login_as(client, "demo", "demo12345")
    detail = await client.get(f"/api/v1/contacts/{contact.id}", headers=owner_headers)
    assert detail.status_code == 200
    dates = detail.json()["dates"]
    assert len(dates) == 1
    assert dates[0]["type"] == "birthday"
    assert dates[0]["calendar"] == "solar"
    assert dates[0]["reminder_lead_days"] == [7, 1]

    # 家庭可见联系人的日期，家庭其他成员同样可读
    member_headers = await login_as(client, "tong", "demo12345")
    member_view = await client.get(f"/api/v1/contacts/{contact.id}", headers=member_headers)
    assert member_view.status_code == 200
    assert len(member_view.json()["dates"]) == 1


async def test_create_direct_contact(client, family_users):
    """创建直接联系人并返回服务端计算的展示名。"""
    owner, _ = family_users
    headers = await login_as(client, "demo", "demo12345")
    response = await client.post(
        "/api/v1/contacts",
        json={"tier": "direct", "name": "陈建国", "nickname": "老爸"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["contact"]["display_name"] == "老爸"
    assert body["contact"]["name"] == "陈建国"


async def test_create_edge_contact_minimal_fields(client, family_users):
    """边缘联系人允许只有昵称的最小信息集。"""
    headers = await login_as(client, "demo", "demo12345")
    response = await client.post(
        "/api/v1/contacts",
        json={"tier": "edge", "nickname": "张小宝"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["contact"]["display_name"] == "张小宝"
    assert body["contact"]["tier"] == "edge"


async def test_duplicate_warning_blocks_creation(client, family_users):
    """同名未确认时返回提醒且不落库；确认后可创建。"""
    owner, _ = family_users
    headers = await login_as(client, "demo", "demo12345")
    payload = {"name": "张伟", "nickname": None}
    first = await client.post("/api/v1/contacts", json=payload, headers=headers)
    assert first.json()["created"] is True

    second = await client.post("/api/v1/contacts", json=payload, headers=headers)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["created"] is False
    assert len(second_body["duplicate_warnings"]) == 1
    assert second_body["duplicate_warnings"][0]["display_name"] == "张伟"

    confirmed = await client.post(
        "/api/v1/contacts", json={**payload, "confirm_duplicate": True}, headers=headers
    )
    assert confirmed.json()["created"] is True


async def test_family_visibility_shared_readonly(client, family_users):
    """家庭可见联系人：另一成员可见但不可改；所有者可改。"""
    owner, member = family_users
    contact = await create_contact_for(
        owner, name="张伟", visibility="family"
    )
    member_headers = await login_as(client, "tong", "demo12345")

    detail = await client.get(f"/api/v1/contacts/{contact.id}", headers=member_headers)
    assert detail.status_code == 200

    forbidden = await client.patch(
        f"/api/v1/contacts/{contact.id}", json={"bio": "篡改"}, headers=member_headers
    )
    assert forbidden.status_code == 403

    owner_headers = await login_as(client, "demo", "demo12345")
    allowed = await client.patch(
        f"/api/v1/contacts/{contact.id}", json={"bio": "球友"}, headers=owner_headers
    )
    assert allowed.status_code == 200
    assert allowed.json()["bio"] == "球友"


async def test_private_contact_hidden_from_family(client, family_users):
    """私密联系人对家庭其他成员完全不可见（404）。"""
    owner, member = family_users
    contact = await create_contact_for(
        owner, name="周明", visibility="private"
    )
    member_headers = await login_as(client, "tong", "demo12345")
    response = await client.get(f"/api/v1/contacts/{contact.id}", headers=member_headers)
    assert response.status_code == 404

    owner_headers = await login_as(client, "demo", "demo12345")
    own_view = await client.get(f"/api/v1/contacts/{contact.id}", headers=owner_headers)
    assert own_view.status_code == 200


async def test_promote_edge_to_direct(client, family_users):
    """一键升级：tier 改为 direct，其余数据无损。"""
    owner, _ = family_users
    contact = await create_contact_for(
        owner, tier="edge", nickname="张小宝", name="小宝"
    )
    headers = await login_as(client, "demo", "demo12345")
    response = await client.post(f"/api/v1/contacts/{contact.id}/promote", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "direct"
    assert body["nickname"] == "张小宝"


async def test_archive_is_soft_delete(client, family_users):
    """归档后列表不可见，但详情仍可读（status=archived）。"""
    owner, _ = family_users
    contact = await create_contact_for(owner, name="王芳", tier="edge")
    headers = await login_as(client, "demo", "demo12345")

    deleted = await client.delete(f"/api/v1/contacts/{contact.id}", headers=headers)
    assert deleted.status_code == 204

    listing = await client.get("/api/v1/contacts", headers=headers)
    assert all(item["id"] != contact.id for item in listing.json())

    detail = await client.get(f"/api/v1/contacts/{contact.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "archived"


async def test_search_matches_nickname(client, family_users):
    """搜索命中昵称（名册式搜索）。"""
    owner, _ = family_users
    await create_contact_for(owner, name="陈建国", nickname="老爸")
    headers = await login_as(client, "demo", "demo12345")
    response = await client.get("/api/v1/contacts", params={"search": "老爸"}, headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["display_name"] == "老爸"


async def test_search_matches_name(client, family_users):
    """搜索命中姓名（单字段模糊匹配，不再拆姓/名两个条件）。"""
    owner, _ = family_users
    await create_contact_for(owner, name="陈建国", nickname="老爸")
    headers = await login_as(client, "demo", "demo12345")
    response = await client.get("/api/v1/contacts", params={"search": "建国"}, headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["name"] == "陈建国"


async def test_duplicate_check_skips_blank_name(client, family_users):
    """姓名留空（只填昵称的 edge 联系人）时同名检测必须跳过姓名条件。

    否则 Contact.name == "" 会命中所有同样留空的 edge 联系人，第二个就建不出来。
    """
    owner, _ = family_users
    await create_contact_for(owner, tier="edge", nickname="张小宝")
    headers = await login_as(client, "demo", "demo12345")

    created = await client.post(
        "/api/v1/contacts", json={"tier": "edge", "nickname": "李二"}, headers=headers
    )
    assert created.json()["created"] is True
    assert created.json()["duplicate_warnings"] == []

    # 只带空姓名探查：库里有「张小宝」同样是空姓名，没有空值守卫就会命中它
    probed = await client.get(
        "/api/v1/contacts/duplicate-check",
        params={"name": ""},
        headers=headers,
    )
    assert probed.status_code == 200
    assert probed.json() == []


async def test_display_name_rule(client, family_users):
    """展示名规则：昵称 > 姓名；姓名与昵称都空（含纯空白）则创建被拒 422。"""
    owner, _ = family_users
    headers = await login_as(client, "demo", "demo12345")

    with_nickname = await client.post(
        "/api/v1/contacts", json={"name": "陈建国", "nickname": "老爸"}, headers=headers
    )
    assert with_nickname.json()["contact"]["display_name"] == "老爸"

    name_only = await client.post(
        "/api/v1/contacts", json={"name": "陈秀兰"}, headers=headers
    )
    assert name_only.json()["contact"]["display_name"] == "陈秀兰"

    blank = await client.post("/api/v1/contacts", json={"name": "   "}, headers=headers)
    assert blank.status_code == 422


async def test_name_length_boundary(client, family_users):
    """姓名列上限 100（原 姓50+名50 的上界不缩水）：满 100 可存，101 被拒。"""
    owner, _ = family_users
    headers = await login_as(client, "demo", "demo12345")

    full = "欧" * 100
    ok = await client.post("/api/v1/contacts", json={"name": full}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["contact"]["name"] == full

    too_long = await client.post("/api/v1/contacts", json={"name": "欧" * 101}, headers=headers)
    assert too_long.status_code == 422


async def test_update_name(client, family_users):
    """改名走 PATCH：单字段更新后展示名与搜索结果同步。"""
    owner, _ = family_users
    contact = await create_contact_for(owner, name="陈建国")
    headers = await login_as(client, "demo", "demo12345")

    updated = await client.patch(
        f"/api/v1/contacts/{contact.id}", json={"name": "陈建军"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "陈建军"
    assert updated.json()["display_name"] == "陈建军"

    found = await client.get("/api/v1/contacts", params={"search": "建军"}, headers=headers)
    assert [r["id"] for r in found.json()] == [contact.id]
