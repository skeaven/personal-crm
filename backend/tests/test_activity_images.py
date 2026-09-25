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
