"""records 模块测试：活动 CRUD（参与者语义）+ 任务 CRUD + D7 隔离与权限。"""

from datetime import UTC, datetime, timedelta

import pytest

from tests.factories import (
    create_activity_for,
    create_contact_for,
    create_family_user,
    create_task_for,
    login_as,
)

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


async def _two_users(client):
    """造同家庭两个用户（demo/tong），返回 (demo用户, tong的headers)。"""
    demo, _ = await create_family_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong", display_name="小彤")
    return demo, await login_as(client, "tong", "demo12345")


# ---------- 活动：创建与参与者 ----------


async def test_create_activity_with_participants(client, make_user, login_headers):
    """创建活动带参与者：返回契约回显参与者，可再按标题搜出。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    mother = await create_contact_for(demo, name="陈秀兰")
    headers = await login_headers("demo", "demo12345")

    resp = await client.post(
        "/api/v1/records/activities",
        json={
            "title": "家庭团圆饭",
            "occurred_at": _NOW.isoformat(),
            "location": "老家",
            "participant_ids": [father.id, mother.id],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "家庭团圆饭"
    assert sorted(body["participant_ids"]) == sorted([father.id, mother.id])

    listed = (await client.get("/api/v1/records/activities?search=团圆", headers=headers)).json()
    assert len(listed) == 1 and listed[0]["id"] == body["id"]


async def test_create_activity_validates_participants_readable(client, make_user, login_headers):
    """参与者必须对创建者可读：传入他人的私密联系人 → 422，活动不落库。"""
    demo, _ = await make_user(username="demo")
    other, _ = await make_user(username="other")
    hidden = await create_contact_for(other, name="私人", visibility="private")
    headers = await login_headers("demo", "demo12345")

    resp = await client.post(
        "/api/v1/records/activities",
        json={"title": "饭局", "participant_ids": [hidden.id]},
        headers=headers,
    )
    assert resp.status_code == 422
    listed = (await client.get("/api/v1/records/activities", headers=headers)).json()
    assert listed == []


async def test_activity_visibility_isolation(client, make_user, login_headers):
    """D7 读取隔离：私密活动对家庭成员不可见；家庭可见活动可见。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    tong_headers = await login_headers("tong", "demo12345")
    await create_activity_for(demo, title="私密饭局", visibility="private")
    await create_activity_for(demo, title="家宴", visibility="family")

    demo_headers = await login_headers("demo", "demo12345")
    mine = (await client.get("/api/v1/records/activities", headers=demo_headers)).json()
    theirs = (await client.get("/api/v1/records/activities", headers=tong_headers)).json()
    assert {a["title"] for a in mine} == {"私密饭局", "家宴"}
    assert [a["title"] for a in theirs] == ["家宴"]


async def test_activity_unreadable_participants_hidden(
    client, make_user, login_headers
):
    """对查看者不可读的参与者只隐藏 id，不出现在返回列表中。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    private_friend = await create_contact_for(
        demo, name="周明", visibility="private"
    )
    family_mate = await create_contact_for(
        demo, name="陈建国", visibility="family"
    )
    await create_activity_for(
        demo, title="聚会", visibility="family",
        participant_contact_ids=[private_friend.id, family_mate.id],
    )
    tong_headers = await login_headers("tong", "demo12345")

    listed = (await client.get("/api/v1/records/activities", headers=tong_headers)).json()
    assert len(listed) == 1
    assert listed[0]["participant_ids"] == [family_mate.id]


# ---------- 活动：更新与删除 ----------


async def test_activity_update_participants_replaced(client, make_user, login_headers):
    """更新活动：participant_ids 提交即全量替换参与者名单。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, name="陈建国")
    mother = await create_contact_for(demo, name="陈秀兰")
    activity = await create_activity_for(
        demo, title="旧标题", participant_contact_ids=[father.id]
    )
    headers = await login_headers("demo", "demo12345")

    resp = await client.patch(
        f"/api/v1/records/activities/{activity.id}",
        json={"title": "新标题", "participant_ids": [mother.id]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["participant_ids"] == [mother.id]


async def test_activity_write_permissions(client, make_user, login_headers):
    """写权限：所有者可改/删；家庭成员可读但写 → 403。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    activity = await create_activity_for(demo, title="家宴", visibility="family")
    tong_headers = await login_headers("tong", "demo12345")

    forbidden = await client.patch(
        f"/api/v1/records/activities/{activity.id}", json={"title": "改"}, headers=tong_headers
    )
    assert forbidden.status_code == 403
    delete_forbidden = await client.delete(
        f"/api/v1/records/activities/{activity.id}", headers=tong_headers
    )
    assert delete_forbidden.status_code == 403

    owner_headers = await login_headers("demo", "demo12345")
    deleted = await client.delete(
        f"/api/v1/records/activities/{activity.id}", headers=owner_headers
    )
    assert deleted.status_code == 204
    gone = await client.get("/api/v1/records/activities", headers=owner_headers)
    assert gone.json() == []


# ---------- 任务 ----------


async def test_task_create_list_ordering(client, make_user, login_headers):
    """任务列表：有截止时间的在前按时间升序，无截止时间的排最后。"""
    demo, _ = await make_user(username="demo")
    headers = await login_headers("demo", "demo12345")
    late = (_NOW + timedelta(days=5)).isoformat()
    soon = (_NOW + timedelta(days=1)).isoformat()

    await client.post("/api/v1/records/tasks", json={"title": "无期限的事"}, headers=headers)
    await client.post(
        "/api/v1/records/tasks", json={"title": "晚的", "due_at": late}, headers=headers
    )
    await client.post(
        "/api/v1/records/tasks", json={"title": "早的", "due_at": soon}, headers=headers
    )

    listed = (await client.get("/api/v1/records/tasks", headers=headers)).json()
    assert [t["title"] for t in listed] == ["早的", "晚的", "无期限的事"]


async def test_task_complete_flow(client, make_user, login_headers):
    """完成任务：status=done 时服务端盖 completed_at，不必客户端传。"""
    demo, _ = await make_user(username="demo")
    task = await create_task_for(demo, title="给老爸打电话")
    headers = await login_headers("demo", "demo12345")

    resp = await client.patch(
        f"/api/v1/records/tasks/{task.id}", json={"status": "done"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done" and body["completed_at"] is not None


async def test_task_visibility_and_permissions(client, make_user, login_headers):
    """任务 D7：私密不可见；家庭可见只读，他人写 → 403。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    family_task = await create_task_for(demo, title="买月饼", visibility="family")
    private_task = await create_task_for(demo, title="私事", visibility="private")
    tong_headers = await login_headers("tong", "demo12345")

    listed = (await client.get("/api/v1/records/tasks", headers=tong_headers)).json()
    assert [t["title"] for t in listed] == ["买月饼"]

    forbidden = await client.patch(
        f"/api/v1/records/tasks/{family_task.id}", json={"status": "done"}, headers=tong_headers
    )
    assert forbidden.status_code == 403
    hidden = await client.get(f"/api/v1/records/tasks/{private_task.id}", headers=tong_headers)
    assert hidden.status_code == 404


async def test_list_activities_filters_by_contact(client, login_headers, make_user, db_session):
    """按 contact_id 过滤只返回该联系人作为参与者的活动。"""
    from app.modules.contacts.models import Contact
    from app.modules.records.models import Activity, ActivityParticipant

    user, _ = await make_user(username="filter_user", password="pw12345678")
    headers = await login_headers("filter_user", "pw12345678")
    dad = Contact(name="陈爸", owner_user_id=user.id, family_id=user.family_id)
    mom = Contact(name="李妈", owner_user_id=user.id, family_id=user.family_id)
    db_session.add_all([dad, mom])
    await db_session.flush()
    with_dad = Activity(title="陪爸钓鱼", owner_user_id=user.id, family_id=user.family_id)
    with_mom = Activity(title="陪妈买菜", owner_user_id=user.id, family_id=user.family_id)
    db_session.add_all([with_dad, with_mom])
    await db_session.flush()
    db_session.add_all(
        [
            ActivityParticipant(activity_id=with_dad.id, contact_id=dad.id),
            ActivityParticipant(activity_id=with_mom.id, contact_id=mom.id),
        ]
    )
    # 必须 commit：db_session 与 HTTP 请求（get_db）是两个独立会话
    await db_session.commit()

    response = await client.get(
        f"/api/v1/records/activities?contact_id={dad.id}", headers=headers
    )

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["陪爸钓鱼"]
