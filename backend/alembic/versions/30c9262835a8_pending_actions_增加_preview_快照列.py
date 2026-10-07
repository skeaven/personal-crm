"""pending_actions 增加 preview 快照列

Revision ID: 30c9262835a8
Revises: dfc278a66ffa
Create Date: 2026-10-07 11:40:55.726263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '30c9262835a8'
down_revision: Union[str, None] = 'dfc278a66ffa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pending_actions', sa.Column('preview', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='确认面板的渲染快照（before/summary），与 payload 分离'))


def downgrade() -> None:
    op.drop_column('pending_actions', 'preview')
