"""备注（notes）端点测试：CRUD、权限隔离、时间线接入（L3 收尾项）。"""

import pytest

from app.modules.records import service as records_service
from app.modules.records.schemas import NoteCreate, NoteUpdate
from tests.factories import create_contact_for

pytestmark = pytest.mark.asyncio


async def test_note_crud_roundtrip(db_session, make_user):
    """创建 → 列表 → 更新 → 删除 全链路。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="陈建国")

    created = await records_service.create_note(
        db_session, demo, NoteCreate(contact_id=contact.id, content="上次聊天提到想换车")
    )
    assert created.id is not None
    assert created.content == "上次聊天提到想换车"
    assert created.contact_id == contact.id

    listed = await records_service.list_contact_notes(db_session, demo, contact_id=contact.id)
    assert [n.id for n in listed] == [created.id]

    updated = await records_service.update_note(
        db_session, demo, created.id, NoteUpdate(content="想换电车，预算 25w")
    )
    assert updated.content == "想换电车，预算 25w"

    await records_service.delete_note(db_session, demo, created.id)
    listed = await records_service.list_contact_notes(db_session, demo, contact_id=contact.id)
    assert listed == []


async def test_note_requires_readable_contact(db_session, make_user):
    """挂到不可见联系人 → 422。"""
    demo, _ = await make_user(username="demo")
    other, _ = await make_user(username="other")
    hidden = await create_contact_for(other, name="私人", visibility="private")

    with pytest.raises(Exception, match="不可见"):
        await records_service.create_note(
            db_session, demo, NoteCreate(contact_id=hidden.id, content="偷看")
        )


async def test_note_visibility_isolation(db_session, make_user):
    """家庭可见备注家人可读；私密联系人的备注他人不可见。"""
    demo, _ = await make_user(username="demo")
    tong, _ = await make_user(username="tong2", family_id=demo.family_id)
    shared = await create_contact_for(demo, name="陈建国")
    private = await create_contact_for(
        demo, name="周明", visibility="private"
    )

    await records_service.create_note(
        db_session, demo, NoteCreate(contact_id=shared.id, content="家人可见的备注")
    )
    await records_service.create_note(
        db_session, demo, NoteCreate(contact_id=private.id, content="私密备注")
    )

    tong_shared = await records_service.list_contact_notes(
        db_session, tong, contact_id=shared.id
    )
    assert [n.content for n in tong_shared] == ["家人可见的备注"]
    tong_private = await records_service.list_contact_notes(
        db_session, tong, contact_id=private.id
    )
    assert tong_private == []


async def test_note_edit_permission(db_session, make_user):
    """只有所有者能改/删备注（家人只读）。"""
    demo, _ = await make_user(username="demo")
    tong, _ = await make_user(username="tong2", family_id=demo.family_id)
    contact = await create_contact_for(demo, name="陈建国")
    note = await records_service.create_note(
        db_session, demo, NoteCreate(contact_id=contact.id, content="原文")
    )

    from app.core.errors import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        await records_service.update_note(
            db_session, tong, note.id, NoteUpdate(content="改你的")
        )


async def test_note_in_contact_timeline(db_session, client, make_user, login_headers):
    """时间线接入：备注以 source=note 出现在联系人时间线里。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="陈建国")
    await records_service.create_note(
        db_session, demo, NoteCreate(contact_id=contact.id, content="时间线里的一条备注")
    )
    await db_session.commit()  # HTTP 请求用独立会话，造数必须先落库
    headers = await login_headers("demo", "demo12345")

    resp = await client.get(f"/api/v1/contacts/{contact.id}/timeline", headers=headers)
    assert resp.status_code == 200
    sources = [item["source"] for item in resp.json()["items"]]
    assert "note" in sources
    note_item = next(i for i in resp.json()["items"] if i["source"] == "note")
    assert "时间线里的一条备注" in note_item["summary"]


async def test_note_rest_crud(client, make_user, login_headers):
    """REST 端点全链路：POST 创建 → GET 列表 → PATCH 改正文 → DELETE 删除。"""
    demo, _ = await make_user(username="demo")
    contact = await create_contact_for(demo, name="陈建国")
    headers = await login_headers("demo", "demo12345")

    created = (
        await client.post(
            "/api/v1/records/notes",
            json={"contact_id": contact.id, "content": "接口创建的备注"},
            headers=headers,
        )
    ).json()
    assert created["content"] == "接口创建的备注"
    assert created["contact_id"] == contact.id
    assert created["owner_display_name"] == "阿澄"

    listed = (
        await client.get(
            f"/api/v1/records/notes?contact_id={contact.id}", headers=headers
        )
    ).json()
    assert [n["id"] for n in listed] == [created["id"]]

    updated = (
        await client.patch(
            f"/api/v1/records/notes/{created['id']}",
            json={"content": "改过的备注"},
            headers=headers,
        )
    ).json()
    assert updated["content"] == "改过的备注"

    resp = await client.delete(f"/api/v1/records/notes/{created['id']}", headers=headers)
    assert resp.status_code == 204
    listed = (
        await client.get(
            f"/api/v1/records/notes?contact_id={contact.id}", headers=headers
        )
    ).json()
    assert listed == []


async def test_note_rest_create_on_invisible_contact(client, make_user, login_headers):
    """往不可见联系人挂备注 → 422（服务层校验经 HTTP 透出）。"""
    demo, _ = await make_user(username="demo")
    other, _ = await make_user(username="other2")
    hidden = await create_contact_for(other, name="私人", visibility="private")
    headers = await login_headers("demo", "demo12345")

    resp = await client.post(
        "/api/v1/records/notes",
        json={"contact_id": hidden.id, "content": "偷看"},
        headers=headers,
    )
    assert resp.status_code == 422
