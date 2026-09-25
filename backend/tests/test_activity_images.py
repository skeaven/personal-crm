"""activity_images 表结构测试：级联删除与排序字段。"""

from sqlalchemy import text


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
