"""L4 语义检索：embeddings 表（pgvector，1024 维）

Revision ID: d5a8c2e17b31
Revises: b8e42c90aa17
Create Date: 2026-09-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5a8c2e17b31'
down_revision: str | None = 'b8e42c90aa17'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VISIBILITY = postgresql.ENUM('private', 'family', name='visibility_enum', create_type=False)
_ENTITY_TYPE = postgresql.ENUM(
    'contact', 'activity', 'gift', 'fund', 'note', name='embedding_entity_enum'
)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    op.create_table('embeddings',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('entity_type', _ENTITY_TYPE, nullable=False, comment='业务实体类型'),
    sa.Column('entity_id', sa.BigInteger(), nullable=False, comment='业务实体 id（元数据关联，无硬 FK）'),
    sa.Column('content', sa.Text(), nullable=False, comment='被向量化的文本快照'),
    sa.Column('content_hash', sa.String(length=64), nullable=False, comment='源内容哈希（增量重建判断）'),
    sa.Column('model', sa.String(length=100), nullable=False, comment='生成用 embedding 模型'),
    sa.Column('embedding', VECTOR(1024), nullable=False, comment='语义向量'),
    sa.Column('owner_user_id', sa.BigInteger(), nullable=False, comment='所有者（创建者），唯一可写'),
    sa.Column('family_id', sa.BigInteger(), nullable=False, comment='所属家庭，服务层保证与所有者一致'),
    sa.Column('visibility', _VISIBILITY, server_default='family', nullable=False, comment='可见性：private 私密 / family 家庭可见只读'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
    sa.ForeignKeyConstraint(['family_id'], ['families.id'], ),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('entity_type', 'entity_id', name='uq_embedding_entity')
    )
    op.create_index(op.f('ix_embeddings_family_id'), 'embeddings', ['family_id'], unique=False)
    op.create_index(op.f('ix_embeddings_owner_user_id'), 'embeddings', ['owner_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_embeddings_owner_user_id'), table_name='embeddings')
    op.drop_index(op.f('ix_embeddings_family_id'), table_name='embeddings')
    op.drop_table('embeddings')
    op.execute("DROP TYPE IF EXISTS embedding_entity_enum")
