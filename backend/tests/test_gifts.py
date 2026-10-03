"""gifts 模块测试：礼物往来与愿望清单 CRUD、搜索过滤、D7 隔离、愿望转礼物。"""

from datetime import date

import pytest

from tests.factories import (
    create_contact_for,
    create_family_user,
    create_gift_for,
    create_wishlist_for,
)

pytestmark = pytest.mark.asyncio


async def _demo_with_family():
    """造 demo 用户；返回用户对象（家庭成员按需另建）。"""
    demo, _ = await create_family_user(username="demo")
    return demo


# ---------- 礼物往来 ----------


async def test_create_gift_with_all_fields(client, make_user, login_headers):
    """创建送出礼物：金额/场合/链接/说明全字段回显，币种默认 CNY。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    headers = await login_headers("demo", "demo12345")

    resp = await client.post(
        "/api/v1/gifts",
        json={
            "contact_id": father.id,
            "direction": "given",
            "title": "龙井茶",
            "occasion": "生日",
            "amount": "388.00",
            "given_at": "2026-09-20",
            "link": "https://example.com/tea",
            "description": "**特调** 明前龙井",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "龙井茶" and body["direction"] == "given"
    assert body["amount"] == "388.00" and body["currency"] == "CNY"
    assert body["given_at"] == "2026-09-20"


async def test_gift_list_search_and_filters(client, make_user, login_headers):
    """礼物列表：关键字搜标题/场合；direction 与 contact_id 可组合过滤。"""
    demo = await _demo_with_family()
    father = await create_contact_for(demo, name="陈建国")
    mother = await create_contact_for(demo, name="陈秀兰")
    await create_gift_for(
        demo, contact_id=father.id, direction="given", title="龙井茶", occasion="生日"
    )
    await create_gift_for(
        demo, contact_id=mother.id, direction="received", title="围巾", occasion="春节"
    )
    await create_gift_for(demo, direction="given", title="钓鱼竿")
    headers = await login_headers("demo", "demo12345")

    searched = (await client.get("/api/v1/gifts?search=茶", headers=headers)).json()
    assert [g["title"] for g in searched] == ["龙井茶"]

    given = (await client.get("/api/v1/gifts?direction=given", headers=headers)).json()
    assert {g["title"] for g in given} == {"龙井茶", "钓鱼竿"}

    for_father = (
        await client.get(f"/api/v1/gifts?contact_id={father.id}&direction=given", headers=headers)
    ).json()
    assert [g["title"] for g in for_father] == ["龙井茶"]


async def test_gift_visibility_isolation_and_permissions(client, make_user, login_headers):
    """D7：私密礼物对家人不可见；家人可读不可写；所有者可删。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    private_gift = await create_gift_for(
        demo, direction="given", title="私物", visibility="private"
    )
    family_gift = await create_gift_for(demo, direction="given", title="家礼", visibility="family")
    tong_headers = await login_headers("tong", "demo12345")

    listed = (await client.get("/api/v1/gifts", headers=tong_headers)).json()
    assert [g["title"] for g in listed] == ["家礼"]

    forbidden = await client.patch(
        f"/api/v1/gifts/{family_gift.id}", json={"amount": "1"}, headers=tong_headers
    )
    assert forbidden.status_code == 403
    hidden = await client.get(f"/api/v1/gifts/{private_gift.id}", headers=tong_headers)
    assert hidden.status_code == 404

    owner_headers = await login_headers("demo", "demo12345")
    deleted = await client.delete(f"/api/v1/gifts/{family_gift.id}", headers=owner_headers)
    assert deleted.status_code == 204


# ---------- 愿望清单 ----------


async def test_wishlist_create_defaults_and_status_filter(client, make_user, login_headers):
    """愿望默认 open；status 过滤只命中对应状态。"""
    demo, _ = await make_user(username="demo")
    mother = await create_contact_for(demo, name="陈秀兰")
    headers = await login_headers("demo", "demo12345")

    created = await client.post(
        "/api/v1/gifts/wishlist",
        json={
            "contact_id": mother.id,
            "title": "按摩仪",
            "amount": "599.00",
            "target_date": "2026-10-01",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "open"

    await create_wishlist_for(demo, title="已买的围巾", status="purchased")
    open_only = (await client.get("/api/v1/gifts/wishlist?status=open", headers=headers)).json()
    assert [w["title"] for w in open_only] == ["按摩仪"]


async def test_wishlist_search(client, make_user, login_headers):
    """愿望关键字搜索命中标题。"""
    demo, _ = await make_user(username="demo")
    await create_wishlist_for(demo, title="紫砂壶")
    await create_wishlist_for(demo, title="钓鱼竿")
    headers = await login_headers("demo", "demo12345")

    found = (await client.get("/api/v1/gifts/wishlist?search=紫砂", headers=headers)).json()
    assert [w["title"] for w in found] == ["紫砂壶"]


async def test_wishlist_convert_to_gift(client, make_user, login_headers):
    """愿望送出转礼物：生成 given 礼物（given_at=今天），愿望置 given 并回链；不可重复转换。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    item = await create_wishlist_for(
        demo, contact_id=father.id, title="钓鱼竿", amount="1200.00", description="达瓦 fisheye"
    )
    headers = await login_headers("demo", "demo12345")

    resp = await client.post(f"/api/v1/gifts/wishlist/{item.id}/convert", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gift"]["direction"] == "given"
    assert body["gift"]["given_at"] == date.today().isoformat()
    assert body["gift"]["title"] == "钓鱼竿"
    assert body["item"]["status"] == "given"
    assert body["item"]["converted_gift_id"] == body["gift"]["id"]

    again = await client.post(f"/api/v1/gifts/wishlist/{item.id}/convert", headers=headers)
    assert again.status_code == 400


async def test_wishlist_convert_permissions(client, make_user, login_headers):
    """转礼物是写操作：家庭成员对家庭可见愿望 → 403。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    item = await create_wishlist_for(demo, title="家中的愿望", visibility="family")
    tong_headers = await login_headers("tong", "demo12345")

    forbidden = await client.post(f"/api/v1/gifts/wishlist/{item.id}/convert", headers=tong_headers)
    assert forbidden.status_code == 403
