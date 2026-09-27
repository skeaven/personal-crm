"""AI 会话索引测试：表结构、归属隔离、列表与删除。"""

from sqlalchemy import text


async def test_ai_session_table_exists(db_session):
    """迁移后表存在且含约定列。"""
    rows = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ai_sessions'"
        )
    )
    columns = {row[0] for row in rows}

    assert {"session_id", "user_id", "title"} <= columns


async def test_session_id_is_primary_key(db_session):
    """session_id 是主键（前端生成的 uuid 天然唯一，不另加自增列）。"""
    rows = await db_session.execute(
        text(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = 'ai_sessions'::regclass AND i.indisprimary"
        )
    )
    primary_keys = {row[0] for row in rows}

    assert primary_keys == {"session_id"}
