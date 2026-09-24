"""联系人资料扩充（2026-09-23）：联系方式/地址/兴趣/毕业院校

字段全部可空文本；院校采用文本列 + distinct 列表（家庭量级免字典表）。

Revision ID: c6d1e7f2a845
Revises: a3f8d21c9e57
Create Date: 2026-09-23

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c6d1e7f2a845'
down_revision: str | None = 'a3f8d21c9e57'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('phone', sa.String(length=30), nullable=True, comment='电话'))
    op.add_column('contacts', sa.Column('qq', sa.String(length=30), nullable=True, comment='QQ 号'))
    op.add_column('contacts', sa.Column('wechat', sa.String(length=50), nullable=True, comment='微信号'))
    op.add_column('contacts', sa.Column('email', sa.String(length=120), nullable=True, comment='邮箱'))
    op.add_column('contacts', sa.Column('current_address', sa.String(length=200), nullable=True, comment='现居地'))
    op.add_column('contacts', sa.Column('family_address', sa.String(length=200), nullable=True, comment='家庭地址'))
    op.add_column('contacts', sa.Column('hobbies', sa.String(length=300), nullable=True, comment='兴趣爱好'))
    op.add_column('contacts', sa.Column('school_name', sa.String(length=100), nullable=True, comment='毕业院校'))


def downgrade() -> None:
    for col in ('school_name', 'hobbies', 'family_address', 'current_address',
                'email', 'wechat', 'qq', 'phone'):
        op.drop_column('contacts', col)
