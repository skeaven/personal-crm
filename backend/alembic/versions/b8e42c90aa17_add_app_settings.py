"""补建 app_settings 表（首个迁移遗漏：模型后加、迁移未同步，新库暴露）

Revision ID: b8e42c90aa17
Revises: c3f7a1d2e409
Create Date: 2026-09-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e42c90aa17'
down_revision: str | None = 'c3f7a1d2e409'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('app_settings',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False, comment='配置键，如 ai.llm'),
    sa.Column('value', postgresql.JSONB(), nullable=False, comment='结构化配置值'),
    sa.Column('updated_by', sa.BigInteger(), nullable=True, comment='最后修改人'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_index(op.f('ix_app_settings_key'), 'app_settings', ['key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_app_settings_key'), table_name='app_settings')
    op.drop_table('app_settings')
