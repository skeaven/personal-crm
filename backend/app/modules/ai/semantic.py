"""ai 模块语义检索：增量对账管线 + cosine 检索（D3/D6.3）。

对账语义（数据变更时的处理策略）：
- 源内容 hash 未变 → 跳过（不重复计费/重算）；
- 新增或内容变更 → 重新生成向量（upsert 到唯一键 entity_type+entity_id）；
- 源数据消失（归档/删除）或向量模型变更 → 清除对应向量行。
管线全量对账、幂等；由设置页手动触发（个人量级秒级完成），实时钩子后续可加。
"""

import hashlib

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.embedding import Embedder, require_embedder
from app.modules.ai.models import Embedding
from app.modules.ai.sources import collect_sources
from app.modules.auth.models import User
from app.services.permission import readable_condition


def _content_hash(content: str) -> str:
    """源内容哈希（sha256 截断 64 位十六进制）。"""
    return hashlib.sha256(content.encode()).hexdigest()


async def rebuild_index(
    db: AsyncSession, user: User, *, embedder: Embedder | None = None
) -> dict:
    """全量对账重建：返回统计（embedded/skipped/removed）。

    embedder 可注入（测试/离线脚本）；缺省按当前配置构建（未配置报明确错误）。
    """
    if embedder is not None:
        config = {"model": "test-embedder"}
        effective_embedder = embedder
    else:
        config, effective_embedder = await require_embedder(db)

    entries = await collect_sources(db, user)
    model_name = str(config["model"])

    existing_rows = (await db.execute(select(Embedding))).scalars().all()
    existing = {(row.entity_type, row.entity_id): row for row in existing_rows}

    to_embed: list = []
    for entry in entries:
        row = existing.get(entry.key())
        unchanged = (
            row is not None
            and row.model == model_name
            and row.content_hash == _content_hash(entry.content)
        )
        if unchanged:
            continue  # 未变更：跳过
        to_embed.append(entry)

    # 清理：源已消失，或模型已更换（旧向量一律重算/移除）
    current_keys = {entry.key() for entry in entries}
    stale_ids = [
        row.id
        for key, row in existing.items()
        if key not in current_keys or row.model != model_name
    ]
    if stale_ids:
        await db.execute(delete(Embedding).where(Embedding.id.in_(stale_ids)))

    embedded = 0
    batch_size = 32
    for start in range(0, len(to_embed), batch_size):
        batch = to_embed[start:start + batch_size]
        vectors = await effective_embedder([entry.content for entry in batch])
        for entry, vector in zip(batch, vectors, strict=True):
            row = existing.get(entry.key())
            if row is None:
                db.add(
                    Embedding(
                        entity_type=entry.entity_type,
                        entity_id=entry.entity_id,
                        content=entry.content,
                        content_hash=_content_hash(entry.content),
                        model=model_name,
                        embedding=vector,
                        owner_user_id=entry.owner_user_id,
                        family_id=entry.family_id,
                        visibility=entry.visibility,
                    )
                )
            else:
                row.content = entry.content
                row.content_hash = _content_hash(entry.content)
                row.model = model_name
                row.embedding = vector
                row.owner_user_id = entry.owner_user_id
                row.family_id = entry.family_id
                row.visibility = entry.visibility
        embedded += len(batch)
    await db.flush()

    return {"embedded": embedded, "skipped": len(entries) - embedded, "removed": len(stale_ids)}


async def search(
    db: AsyncSession,
    user: User,
    query: str,
    *,
    embedder: Embedder | None = None,
    limit: int = 8,
) -> list[dict]:
    """语义搜索：查询向量化后按 cosine 距离取最近的可读向量。

    返回 [{entity_type, entity_id, content, distance}]；仅当前配置模型下的向量参与。
    """
    if embedder is not None:
        config = {"model": "test-embedder"}
        effective_embedder = embedder
    else:
        config, effective_embedder = await require_embedder(db)

    query_vector = (await effective_embedder([query]))[0]
    model_name = str(config["model"])

    distance = Embedding.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(Embedding, distance)
        .where(
            readable_condition(Embedding, user),
            Embedding.model == model_name,
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).all())

    return [
        {
            "entity_type": embedding.entity_type,
            "entity_id": embedding.entity_id,
            "content": embedding.content,
            "distance": round(float(dist), 4),
        }
        for embedding, dist in rows
    ]
