"""活动图片测试：表结构、级联删除、鉴权读取与缩略图变体。"""

import io

import pytest
from PIL import Image
from sqlalchemy import text

from app.services import storage


@pytest.fixture(autouse=True)
def _isolated_upload_root(tmp_path, monkeypatch):
    """上传根目录指向临时目录，避免污染项目 backend/uploads。"""
    from app.core.config import get_settings

    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _jpeg_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    """造一张可解码的 JPEG（缩略图用例需要真实图片，且原图要明显大于缩略图）。"""
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, "JPEG")
    return buffer.getvalue()


async def _make_activity_with_image(db, user, visibility: str = "family"):
    """造一个带图的活动，返回 (activity_id, image_id)。

    图片走真实的 save_temp → promote_temp 流程；必须 commit —— db_session 与
    HTTP 请求（get_db）是两个独立会话，未提交的数据对端点不可见。
    """
    from app.modules.records.models import Activity, ActivityImage

    temp_path = storage.save_temp(user.id, "p.jpg", _jpeg_bytes())
    full, thumb = storage.promote_temp(temp_path, user_id=user.id, kind="activities")
    activity = Activity(
        title="带图活动", owner_user_id=user.id, family_id=user.family_id, visibility=visibility
    )
    db.add(activity)
    await db.flush()
    image = ActivityImage(activity_id=activity.id, path=full, thumb_path=thumb, sort_order=0)
    db.add(image)
    await db.commit()
    return activity.id, image.id


async def test_activity_image_table_exists(db_session):
    """迁移后表存在且含约定列。"""
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'activity_images'"
        )
    )
    columns = {row[0] for row in rows}

    assert {"activity_id", "path", "thumb_path", "sort_order"} <= columns


async def test_deleting_activity_cascades_images(db_session, make_user):
    """删除活动时图片行级联删除（文件删除由 service 另行负责）。"""
    from app.modules.records.models import Activity, ActivityImage

    user, _ = await make_user(username="owner", password="pw12345678")
    activity = Activity(title="聚会", owner_user_id=user.id, family_id=user.family_id)
    db_session.add(activity)
    await db_session.flush()
    db_session.add(
        ActivityImage(
            activity_id=activity.id,
            path="activities/a.jpg",
            thumb_path="activities/a.thumb.jpg",
            sort_order=0,
        )
    )
    await db_session.flush()

    await db_session.execute(Activity.__table__.delete().where(Activity.id == activity.id))
    await db_session.flush()

    remaining = await db_session.execute(
        text("SELECT count(*) FROM activity_images WHERE activity_id = :aid"),
        {"aid": activity.id},
    )
    assert remaining.scalar_one() == 0


async def test_read_activity_image_as_owner(client, login_headers, make_user, db_session):
    """所有者能读到活动图片。"""
    user, _ = await make_user(username="img_owner", password="pw12345678")
    headers = await login_headers("img_owner", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, user)

    response = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


async def test_read_thumbnail_variant(client, login_headers, make_user, db_session):
    """size=thumb 返回缩略图（体积小于原图）。"""
    user, _ = await make_user(username="thumb_owner", password="pw12345678")
    headers = await login_headers("thumb_owner", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, user)

    full = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)
    thumb = await client.get(
        f"/api/v1/records/activities/images/{image_id}?size=thumb", headers=headers
    )

    assert thumb.status_code == 200
    assert len(thumb.content) < len(full.content)


async def test_read_private_activity_image_by_other_user_is_404(
    client, login_headers, make_user, db_session
):
    """他人私有活动的图片按 404 处理，不泄露存在性。"""
    owner, _ = await make_user(username="priv_owner", password="pw12345678")
    await make_user(username="priv_other", password="pw12345678")
    headers = await login_headers("priv_other", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, owner, visibility="private")

    response = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)

    assert response.status_code == 404


async def test_activities_route_does_not_shadow_images_route(
    client, login_headers, make_user, db_session
):
    """确认 /activities/images/{id} 没被 /activities/{id} 抢先匹配（否则 422）。"""
    user, _ = await make_user(username="route_owner", password="pw12345678")
    headers = await login_headers("route_owner", "pw12345678")
    _, image_id = await _make_activity_with_image(db_session, user)

    response = await client.get(f"/api/v1/records/activities/images/{image_id}", headers=headers)

    assert response.status_code != 422


async def test_read_activity_image_requires_login(client, login_headers, make_user, db_session):
    """图片必须登录才能读（不做静态挂载）。"""
    user, _ = await make_user(username="anon_owner", password="pw12345678")
    _, image_id = await _make_activity_with_image(db_session, user)

    response = await client.get(f"/api/v1/records/activities/images/{image_id}")

    assert response.status_code == 401


# ---------- 活动 CRUD 集成图片（全量替换语义）----------


def _upload(name: str) -> dict:
    """构造一张可解码图片的 multipart 体。"""
    return {"file": (name, _jpeg_bytes((40, 40)), "image/jpeg")}


async def _temp_path(client, headers: dict, name: str) -> str:
    """上传一张临时图并返回其路径（表单提交时引用）。"""
    response = await client.post("/api/v1/uploads/temp", files=_upload(name), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["temp_path"]


async def test_create_activity_with_images(client, login_headers, make_user):
    """新建活动带两张临时图：数组顺序即 sort_order，且临时文件已移入正式区。"""
    await make_user(username="creator", password="pw12345678")
    headers = await login_headers("creator", "pw12345678")
    first = await _temp_path(client, headers, "a.jpg")
    second = await _temp_path(client, headers, "b.jpg")

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "春游", "images": [{"temp_path": first}, {"temp_path": second}]},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    images = response.json()["images"]
    assert [image["sort_order"] for image in images] == [0, 1]
    assert not (storage.upload_root() / first).exists()
    assert not (storage.upload_root() / second).exists()


async def test_create_activity_rejects_other_users_temp_path(client, login_headers, make_user):
    """把别人的临时图认领进自己的活动必须被拒（Review Focus #1）。"""
    await make_user(username="victim", password="pw12345678")
    await make_user(username="attacker", password="pw12345678")
    victim_headers = await login_headers("victim", "pw12345678")
    attacker_headers = await login_headers("attacker", "pw12345678")
    stolen = await _temp_path(client, victim_headers, "v.jpg")

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "偷图", "images": [{"temp_path": stolen}]},
        headers=attacker_headers,
    )

    assert response.status_code == 422
    assert "临时" in response.json()["message"]


async def test_create_activity_rejects_traversal_temp_path(client, login_headers, make_user):
    """temp_path 里带 .. 必须被拒（Review Focus #2）。"""
    await make_user(username="walker", password="pw12345678")
    headers = await login_headers("walker", "pw12345678")

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "穿越", "images": [{"temp_path": "tmp/1/../../etc/passwd"}]},
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_activity_rejects_both_id_and_temp_path(client, login_headers, make_user):
    """图片项同时给 id 与 temp_path 属于语义歧义，拒绝。"""
    await make_user(username="ambiguous", password="pw12345678")
    headers = await login_headers("ambiguous", "pw12345678")

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "歧义", "images": [{"id": 1, "temp_path": "tmp/1/x.jpg"}]},
        headers=headers,
    )

    assert response.status_code == 422


async def test_activity_rejects_more_than_20_images(client, login_headers, make_user):
    """每活动最多 20 张。"""
    await make_user(username="many", password="pw12345678")
    headers = await login_headers("many", "pw12345678")

    response = await client.post(
        "/api/v1/records/activities",
        json={"title": "太多", "images": [{"id": index} for index in range(21)]},
        headers=headers,
    )

    assert response.status_code == 422


async def test_update_activity_replaces_images_wholesale(client, login_headers, make_user):
    """编辑全量替换：保留一项、删掉未出现的旧图，顺序按提交数组重排。"""
    await make_user(username="editor", password="pw12345678")
    headers = await login_headers("editor", "pw12345678")
    created = (
        await client.post(
            "/api/v1/records/activities",
            json={
                "title": "原活动",
                "images": [
                    {"temp_path": await _temp_path(client, headers, "1.jpg")},
                    {"temp_path": await _temp_path(client, headers, "2.jpg")},
                ],
            },
            headers=headers,
        )
    ).json()
    first_id, second_id = (image["id"] for image in created["images"])

    updated = await client.patch(
        f"/api/v1/records/activities/{created['id']}",
        json={
            "images": [
                {"id": second_id},
                {"temp_path": await _temp_path(client, headers, "3.jpg")},
            ]
        },
        headers=headers,
    )

    assert updated.status_code == 200, updated.text
    images = updated.json()["images"]
    assert images[0]["id"] == second_id
    assert first_id not in [image["id"] for image in images]


async def test_update_activity_rejects_foreign_image_id(client, login_headers, make_user):
    """保留项的 id 必须属于本活动，否则拒绝（防把他人图片挂到自己活动上）。"""
    await make_user(username="owner_x", password="pw12345678")
    await make_user(username="owner_y", password="pw12345678")
    headers_x = await login_headers("owner_x", "pw12345678")
    headers_y = await login_headers("owner_y", "pw12345678")
    mine = (
        await client.post(
            "/api/v1/records/activities",
            json={"title": "我的活动", "images": [{"temp_path": await _temp_path(client, headers_x, "m.jpg")}]},
            headers=headers_x,
        )
    ).json()
    theirs = (
        await client.post(
            "/api/v1/records/activities",
            json={"title": "他的活动", "images": [{"temp_path": await _temp_path(client, headers_y, "t.jpg")}]},
            headers=headers_y,
        )
    ).json()
    their_image_id = theirs["images"][0]["id"]

    response = await client.patch(
        f"/api/v1/records/activities/{mine['id']}",
        json={"images": [{"id": their_image_id}]},
        headers=headers_x,
    )

    assert response.status_code == 422


async def test_delete_activity_removes_image_files(client, login_headers, make_user):
    """删除活动后，图片文件也被清掉（延迟到事务提交后执行）。"""
    await make_user(username="deleter", password="pw12345678")
    headers = await login_headers("deleter", "pw12345678")
    created = (
        await client.post(
            "/api/v1/records/activities",
            json={"title": "待删", "images": [{"temp_path": await _temp_path(client, headers, "d.jpg")}]},
            headers=headers,
        )
    ).json()
    activity_id = created["id"]

    from app.modules.records.models import ActivityImage
    from app.core.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        image = await session.get(ActivityImage, created["images"][0]["id"])
        stored_path = image.path

    assert (storage.upload_root() / stored_path).is_file()

    response = await client.delete(f"/api/v1/records/activities/{activity_id}", headers=headers)

    assert response.status_code == 204
    assert not (storage.upload_root() / stored_path).exists()
