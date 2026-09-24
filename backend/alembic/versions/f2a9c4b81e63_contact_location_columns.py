"""contacts 增加地理位置四列（D14：location 文本 + 坐标缓存）

Revision ID: f2a9c4b81e63
Revises: d5a8c2e17b31
Create Date: 2026-09-22

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2a9c4b81e63'
down_revision: str | None = 'd5a8c2e17b31'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'contacts',
        sa.Column('location', sa.String(length=200), nullable=True, comment='所在地文本，保存时经 geo 解析'),
    )
    op.add_column(
        'contacts',
        sa.Column('location_lng', sa.Double(), nullable=True, comment='经度缓存（location 变更才重算）'),
    )
    op.add_column(
        'contacts',
        sa.Column('location_lat', sa.Double(), nullable=True, comment='纬度缓存'),
    )
    op.add_column(
        'contacts',
        sa.Column('location_source', sa.String(length=10), nullable=True, comment='坐标来源：amap/static/none'),
    )
    op.add_column(
        'contacts',
        sa.Column('location_province', sa.String(length=50), nullable=True, comment='所属省级名称（地图 choropleth 聚合维度）'),
    )


def downgrade() -> None:
    op.drop_column('contacts', 'location_province')
    op.drop_column('contacts', 'location_source')
    op.drop_column('contacts', 'location_lat')
    op.drop_column('contacts', 'location_lng')
    op.drop_column('contacts', 'location')
