"""提醒引擎（D22）：reminders 表——三源扫描的幂等重建目标

UNIQUE(user_id, source, ref_id, due_date)：同一来源同一事项同一到期日只有一条；
已读（read_at 非空）后同键不再复活，源头消失时未读清理。

Revision ID: b8e9d4f3a276
Revises: e79b6a656db2
Create Date: 2026-09-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e9d4f3a276'
down_revision: str | None = 'e79b6a656db2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reminders',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='提醒归属用户（按用户权限口径生成）'),
        sa.Column('family_id', sa.BigInteger(), nullable=False, comment='冗余家庭 ID'),
        sa.Column('source', sa.String(length=20), nullable=False, comment='来源：date/task/repayment'),
        sa.Column('ref_id', sa.BigInteger(), nullable=False, comment='来源业务 id'),
        sa.Column('due_date', sa.Date(), nullable=False, comment='到期日（幂等键组成部分）'),
        sa.Column('days_left', sa.Integer(), nullable=False, comment='生成时点的剩余天数快照'),
        sa.Column('title', sa.String(length=200), nullable=False, comment='提醒文案（生成时点快照）'),
        sa.Column('contact_id', sa.BigInteger(), nullable=True, comment='关联联系人（跳转用）'),
        sa.Column('channel', sa.String(length=10), nullable=False, server_default='inapp', comment='通知渠道：inapp（email 预留）'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True, comment='已读时间；NULL=未读'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['family_id'], ['families.id']),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source', 'ref_id', 'due_date', name='uq_reminder_once'),
    )
    op.create_index('ix_reminders_user_unread', 'reminders', ['user_id', 'read_at'])


def downgrade() -> None:
    op.drop_index('ix_reminders_user_unread', table_name='reminders')
    op.drop_table('reminders')
