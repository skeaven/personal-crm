"""重要日期 CRUD 测试：公历/农历校验、所有权权限、可见性跟随联系人。"""

import pytest

from tests.factories import (
    create_contact_for,
    create_date_for,
    create_family_user,
)

pytestmark = pytest.mark.asyncio


async def test_create_solar_and_lunar_dates(client, make_user, login_headers):
    """创建公历/农历日期均回显于详情契约；农历记录带中文标签字段供前端复用。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    mother = await create_contact_for(demo, name="陈秀兰")
    headers = await login_headers("demo", "demo12345")

    solar = await client.post(
        f"/api/v1/contacts/{father.id}/dates",
        json={
            "type": "birthday", "calendar": "solar", "date_solar": "1958-05-12",
            "reminder_lead_days": [7, 1],
        },
        headers=headers,
    )
    assert solar.status_code == 200, solar.text
    assert any(d["date_solar"] == "1958-05-12" for d in solar.json()["dates"])

    lunar = await client.post(
        f"/api/v1/contacts/{mother.id}/dates",
        json={
            "type": "birthday", "calendar": "lunar",
            "lunar_month": 3, "lunar_day": 3, "reminder_lead_days": [7],
        },
        headers=headers,
    )
    assert lunar.status_code == 200, lunar.text
    created = [d for d in lunar.json()["dates"] if d["calendar"] == "lunar"]
    assert created and created[0]["lunar_month"] == 3 and created[0]["lunar_day"] == 3


async def test_create_date_field_validation(client, make_user, login_headers):
    """字段校验：solar 必须有 date_solar；lunar 必须有合法月日；混合/越界 → 422。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    headers = await login_headers("demo", "demo12345")

    solar_missing = await client.post(
        f"/api/v1/contacts/{father.id}/dates",
        json={"type": "birthday", "calendar": "solar", "reminder_lead_days": []},
        headers=headers,
    )
    assert solar_missing.status_code == 422

    lunar_missing = await client.post(
        f"/api/v1/contacts/{father.id}/dates",
        json={"type": "birthday", "calendar": "lunar", "lunar_day": 3},
        headers=headers,
    )
    assert lunar_missing.status_code == 422

    lunar_out_of_range = await client.post(
        f"/api/v1/contacts/{father.id}/dates",
        json={
            "type": "birthday", "calendar": "lunar",
            "lunar_month": 13, "lunar_day": 31,
        },
        headers=headers,
    )
    assert lunar_out_of_range.status_code == 422

    mixed = await client.post(
        f"/api/v1/contacts/{father.id}/dates",
        json={"type": "birthday", "calendar": "lunar", "date_solar": "1958-05-12"},
        headers=headers,
    )
    assert mixed.status_code == 422


async def test_update_and_delete_date(client, make_user, login_headers):
    """更新与删除：改提前提醒量生效；删除后详情不再包含。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    headers = await login_headers("demo", "demo12345")

    created = await client.post(
        f"/api/v1/contacts/{father.id}/dates",
        json={
            "type": "birthday", "calendar": "solar", "date_solar": "1958-05-12",
            "reminder_lead_days": [7],
        },
        headers=headers,
    )
    date_id = created.json()["dates"][0]["id"]

    patched = await client.patch(
        f"/api/v1/contacts/{father.id}/dates/{date_id}",
        json={"reminder_lead_days": [30, 7, 1], "title": "老爷子生日"},
        headers=headers,
    )
    assert patched.status_code == 200
    target = [d for d in patched.json()["dates"] if d["id"] == date_id][0]
    assert target["reminder_lead_days"] == [30, 7, 1] and target["title"] == "老爷子生日"

    deleted = await client.delete(
        f"/api/v1/contacts/{father.id}/dates/{date_id}", headers=headers
    )
    assert deleted.status_code == 204
    after = (await client.get(f"/api/v1/contacts/{father.id}", headers=headers)).json()
    assert all(d["id"] != date_id for d in after["dates"])


async def test_date_write_permissions(client, make_user, login_headers):
    """写权限：家庭可见联系人的日期也只有创建者能改/删（D7 只读共享）。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    father = await create_contact_for(demo, name="陈建国", visibility="family")
    existing = await create_date_for(
        demo, contact_id=father.id, type="birthday", calendar="solar",
        date_solar="1958-05-12", reminder_lead_days=[7],
    )
    tong_headers = await login_headers("tong", "demo12345")

    forbidden_create = await client.post(
        f"/api/v1/contacts/{father.id}/dates",
        json={"type": "anniversary", "calendar": "solar", "date_solar": "1980-01-01"},
        headers=tong_headers,
    )
    assert forbidden_create.status_code == 403

    forbidden_patch = await client.patch(
        f"/api/v1/contacts/{father.id}/dates/{existing.id}",
        json={"reminder_lead_days": [1]},
        headers=tong_headers,
    )
    assert forbidden_patch.status_code == 403

    forbidden_delete = await client.delete(
        f"/api/v1/contacts/{father.id}/dates/{existing.id}", headers=tong_headers
    )
    assert forbidden_delete.status_code == 403


async def test_date_visibility_follows_contact(client, make_user, login_headers):
    """日期可见性跟随联系人：私密联系人的日期对家人不可见。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    private_friend = await create_contact_for(
        demo, name="周明", visibility="private"
    )
    headers = await login_headers("demo", "demo12345")

    created = await client.post(
        f"/api/v1/contacts/{private_friend.id}/dates",
        json={"type": "birthday", "calendar": "solar", "date_solar": "1990-06-01"},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["visibility"] == "private"

    tong_headers = await login_headers("tong", "demo12345")
    hidden = await client.get(f"/api/v1/contacts/{private_friend.id}", headers=tong_headers)
    assert hidden.status_code == 404  # 私密联系人本身不可见，日期随之不可达
