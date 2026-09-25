"""activity_images

Revision ID: 77ce10ba342f
Revises: c6d1e7f2a845
Create Date: 2026-09-25 21:21:46.274568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77ce10ba342f'
down_revision: Union[str, None] = 'c6d1e7f2a845'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 图片行随活动级联删除；文件本身由应用层在事务提交后清理（app/services/storage.py）
    op.create_table('activity_images',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('activity_id', sa.BigInteger(), nullable=False, comment='所属活动'),
    sa.Column('path', sa.String(length=500), nullable=False, comment='正式区相对路径'),
    sa.Column('thumb_path', sa.String(length=500), nullable=False, comment='缩略图相对路径'),
    sa.Column('sort_order', sa.Integer(), nullable=False, comment='展示顺序，升序'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activity_images_activity_id'), 'activity_images', ['activity_id'], unique=False)
    op.create_index(op.f('ix_activity_images_sort_order'), 'activity_images', ['sort_order'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_activity_images_sort_order'), table_name='activity_images')
    op.drop_index(op.f('ix_activity_images_activity_id'), table_name='activity_images')
    op.drop_table('activity_images')
