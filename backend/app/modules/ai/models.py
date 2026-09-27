"""ai 模块 ORM 模型：PendingAction（D11 确认队列）+ Embedding（D3/D6.3 语义向量）
+ AiSession（助理会话索引）。"""

from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import OwnershipMixin, TimestampMixin

PENDING_STATUS_VALUES = ("pending", "approved", "rejected", "expired", "executed")


class PendingAction(Base, TimestampMixin):
    """AI 写入提议：agent 提议 → 用户界面确认 → 落库（D11 工具档位）。"""

    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("families.id"), index=True)
    requested_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    tool_name: Mapped[str] = mapped_column(String(100), comment="MCP 工具名")
    payload: Mapped[dict] = mapped_column(JSONB, comment="工具入参")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="agent 提议理由")
    status: Mapped[str] = mapped_column(
        Enum(*PENDING_STATUS_VALUES, name="pending_status_enum"),
        default="pending",
        server_default="pending",
        comment="提议状态机",
    )
    decided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True, comment="确认人"
    )
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="执行结果摘要")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


EMBEDDING_DIM = 1024

# 可向量化实体类型（随管线扩充）
EMBEDDING_ENTITY_VALUES = ("contact", "activity", "gift", "fund", "note")


class Embedding(Base, OwnershipMixin):
    """语义向量：一实体一向量，与业务数据经 (entity_type, entity_id) 元数据关联。

    不设硬 FK：业务记录删除由对账管线清理向量；content_hash 支持增量重建
    （内容没变不重算）；model 记录生成模型，换模型时全量重建。
    维度固定 1024（D6.3 落地决策：OpenAI text-embedding-3 可 dimensions 截断、
    智谱 embedding-3 支持 dims=1024、本地 bge-m3 原生 1024——换供应商不换维度）。
    可见性快照于向量化时刻（D7），读取时仍按 readable_condition 过滤。
    """

    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_embedding_entity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(
        Enum(*EMBEDDING_ENTITY_VALUES, name="embedding_entity_enum"),
        comment="业务实体类型",
    )
    entity_id: Mapped[int] = mapped_column(BigInteger, comment="业务实体 id（元数据关联，无硬 FK）")
    content: Mapped[str] = mapped_column(Text, comment="被向量化的文本快照")
    content_hash: Mapped[str] = mapped_column(String(64), comment="源内容哈希（增量重建判断）")
    model: Mapped[str] = mapped_column(String(100), comment="生成用 embedding 模型")
    embedding: Mapped[list] = mapped_column(VECTOR(EMBEDDING_DIM), comment="语义向量")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )


class AiSession(Base, TimestampMixin):
    """AI 会话索引：只承载列表展示与归属校验。

    对话内容本身由 LangGraph checkpointer 按 thread_id 存（D20），
    所以本表字段保持最小；thread_id 是 checkpointer 的实现细节，不入业务表。
    """

    __tablename__ = "ai_sessions"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="前端生成的会话标识（uuid）"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True, comment="归属用户"
    )
    title: Mapped[str] = mapped_column(String(100), comment="取首条用户消息前若干字")
