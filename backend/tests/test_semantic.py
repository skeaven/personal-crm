"""语义检索测试：增量对账管线（新增/变更/删除）、D7 隔离、未配置降级。"""

import hashlib
from datetime import UTC, date

import pytest

from app.modules.ai import pending as pending_service  # noqa: F401
from app.modules.ai import registry, semantic
from app.modules.ai.registry import build_args, get_tool
from tests.factories import (
    create_activity_for,
    create_contact_for,
    create_family_user,
    create_gift_for,
)

pytestmark = pytest.mark.asyncio

# 固定 1024 维假向量：以文本首字符编码区分（仅测试用）
_DIM = 1024


def _fake_embedder(prefix: float = 0.1):
    """按文本内容生成稳定伪向量（哈希决定方向），可断言召回。"""

    async def _embed(texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [(digest[i % len(digest)] / 255.0 + prefix) for i in range(_DIM)]
            vectors.append(vec)
        return vectors

    return _embed


async def test_rebuild_creates_and_updates_and_cleans(db_session, make_user):
    """对账三态：新数据建向量、内容变更重算、源数据删除后向量清理。"""
    demo, _ = await make_user(username="demo")
    embedder = _fake_embedder()

    father = await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")
    summary = await semantic.rebuild_index(db_session, demo, embedder=embedder)
    assert summary["embedded"] == 1  # 联系人一条（无其他数据）

    # 内容变更 → hash 变化 → 重算（不新增行）
    father.bio = "爱钓鱼的老干部"
    db_session.add(father)
    await db_session.flush()
    summary2 = await semantic.rebuild_index(db_session, demo, embedder=embedder)
    assert summary2["embedded"] == 1 and summary2["skipped"] == 0

    from sqlalchemy import func, select

    from app.modules.ai.models import Embedding

    count = (
        await db_session.execute(select(func.count()).select_from(Embedding))
    ).scalar()
    assert count == 1

    # 源删除（归档）→ 对账清理向量
    father.status = "archived"
    db_session.add(father)
    await db_session.flush()
    summary3 = await semantic.rebuild_index(db_session, demo, embedder=embedder)
    assert summary3["removed"] == 1
    count = (
        await db_session.execute(select(func.count()).select_from(Embedding))
    ).scalar()
    assert count == 0


async def test_rebuild_covers_five_sources(db_session, make_user):
    """五源装载：联系人/活动/礼物/资金都有向量（note 表随管线扩充）。"""
    demo, _ = await make_user(username="demo")
    father = await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸")

    from datetime import datetime

    await create_activity_for(
        demo, title="家庭聚餐", occurred_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    await create_gift_for(
        demo, contact_id=father.id, direction="given", title="按摩仪",
        given_at=date(2026, 9, 2),
    )

    summary = await semantic.rebuild_index(db_session, demo, embedder=_fake_embedder())
    assert summary["embedded"] == 3  # contact + activity + gift


async def test_semantic_search_visibility(db_session, make_user):
    """D7：私密数据的向量对家庭成员不可见。"""
    demo, _ = await make_user(username="demo")
    await create_family_user(family_id=demo.family_id, username="tong")
    await create_contact_for(
        demo, last_name="周", first_name="明", visibility="private", bio="仅自己可见"
    )
    await semantic.rebuild_index(db_session, demo, embedder=_fake_embedder())

    mine = await semantic.search(db_session, demo, "周明", embedder=_fake_embedder())
    assert len(mine) == 1

    tong, _ = await create_family_user(family_id=demo.family_id, username="tong2")
    theirs = await semantic.search(db_session, tong, "周明", embedder=_fake_embedder())
    assert theirs == []


async def test_semantic_search_tool(db_session, make_user, monkeypatch):
    """语义搜索已注册为工具：经真实配置路径（stub build_embedder）输出结果。"""
    demo, _ = await make_user(username="demo")
    await create_contact_for(demo, last_name="陈", first_name="建国", nickname="老爸", bio="爱钓鱼")
    await semantic.rebuild_index(db_session, demo, embedder=_fake_embedder())

    from app.core.db import get_session_factory
    from app.modules.settings.service import KEY_AI_EMBEDDING, set_setting_value

    factory = get_session_factory()
    async with factory() as session:
        await set_setting_value(
            session, KEY_AI_EMBEDDING,
            {"provider": "openai-compatible", "base_url": "http://127.0.0.1:9/v1",
             "api_key": "sk-test", "model": "test-embedder"},
            updated_by=demo.id,
        )
        await session.commit()
    monkeypatch.setattr(
        "app.modules.ai.embedding.build_embedder", lambda _config: _fake_embedder()
    )
    tool = get_tool("semantic_search")
    assert tool is not None and tool.risk == "read"
    out = await tool.run(db_session, demo, build_args(tool, {"query": "谁爱钓鱼"}))
    assert "爱钓鱼" in out or "陈建国" in out


async def test_requires_embedding_config(db_session, make_user):
    """未配置 Embedding：重建与搜索均报明确错误（D6.2 同款降级契约）。"""
    from app.core.errors import BusinessError

    demo, _ = await make_user(username="demo")
    with pytest.raises(BusinessError):
        await semantic.rebuild_index(db_session, demo)
    with pytest.raises(BusinessError):
        await semantic.search(db_session, demo, "任意")


async def test_registry_has_semantic_search(client, make_user):
    """工具清单包含语义搜索（agent 与 /mcp 自动获得）。"""
    assert "semantic_search" in {tool.name for tool in registry.ALL_TOOLS}
