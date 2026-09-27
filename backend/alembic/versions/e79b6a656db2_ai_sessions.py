"""ai_sessions

Revision ID: e79b6a656db2
Revises: 77ce10ba342f
Create Date: 2026-09-27 21:17:55.851690

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e79b6a656db2'
down_revision: Union[str, None] = '77ce10ba342f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 只建会话索引表：autogenerate 顺带产出的既有 schema 漂移（列注释、app_settings
    # 唯一约束）与本任务无关，故意剔除，避免把已知漂移固化进版本历史。
    # 对话内容由 LangGraph checkpointer 另存，本表不含 thread_id。
    op.create_table('ai_sessions',
    sa.Column('session_id', sa.String(length=64), nullable=False, comment='前端生成的会话标识（uuid）'),
    sa.Column('user_id', sa.BigInteger(), nullable=False, comment='归属用户'),
    sa.Column('title', sa.String(length=100), nullable=False, comment='取首条用户消息前若干字'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('session_id')
    )
    op.create_index(op.f('ix_ai_sessions_user_id'), 'ai_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_sessions_user_id'), table_name='ai_sessions')
    op.drop_table('ai_sessions')
