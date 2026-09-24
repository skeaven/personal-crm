"""L3 原子表：活动参与者关联 + gifts/wishlist_items/fund_flows

- activities 弃用 contact_id（2026-09-21 定稿：一次活动对多名参与者），
  存量单联系人数据迁入 activity_participants；
- 礼物往来 / 愿望清单 / 资金往来按建表先行纪律落表（功能随 L3 迭代交付）。

Revision ID: c3f7a1d2e409
Revises: 9732cfa9ee05
Create Date: 2026-09-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f7a1d2e409'
down_revision: str | None = '9732cfa9ee05'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# visibility_enum 已由首个迁移创建，此处仅引用（否则 CREATE TYPE 重复报错）
_VISIBILITY = postgresql.ENUM('private', 'family', name='visibility_enum', create_type=False)
_D7_COLUMNS = [
    sa.Column('owner_user_id', sa.BigInteger(), nullable=False, comment='所有者（创建者），唯一可写'),
    sa.Column('family_id', sa.BigInteger(), nullable=False, comment='所属家庭，服务层保证与所有者一致'),
    sa.Column('visibility', _VISIBILITY, server_default='family', nullable=False, comment='可见性：private 私密 / family 家庭可见只读'),
]
_D7_CONSTRAINTS = [
    sa.ForeignKeyConstraint(['family_id'], ['families.id'], ),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
]
_TIMESTAMPS = [
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
]


def upgrade() -> None:
    # 1) 活动参与者桥表 + 存量数据迁移 + 弃用单联系人外键
    op.create_table('activity_participants',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('activity_id', sa.BigInteger(), nullable=False, comment='所属活动'),
    sa.Column('contact_id', sa.BigInteger(), nullable=False, comment='参与者联系人'),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id', 'contact_id', name='uq_activity_participant')
    )
    op.create_index(op.f('ix_activity_participants_activity_id'), 'activity_participants', ['activity_id'], unique=False)
    op.create_index(op.f('ix_activity_participants_contact_id'), 'activity_participants', ['contact_id'], unique=False)
    op.execute(
        'INSERT INTO activity_participants (activity_id, contact_id) '
        'SELECT id, contact_id FROM activities WHERE contact_id IS NOT NULL'
    )
    op.drop_index(op.f('ix_activities_contact_id'), table_name='activities')
    op.drop_column('activities', 'contact_id')

    # 2) 礼物往来
    op.create_table('gifts',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('contact_id', sa.BigInteger(), nullable=True, comment='对象联系人'),
    sa.Column('direction', sa.Enum('given', 'received', name='gift_direction_enum'), nullable=False, comment='given 送出 / received 收到'),
    sa.Column('title', sa.String(length=200), nullable=False, comment='礼物名称'),
    sa.Column('occasion', sa.String(length=100), nullable=True, comment='场合（生日/婚礼/探病…自由文本）'),
    sa.Column('amount', sa.Numeric(12, 2), nullable=True, comment='金额'),
    sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False, comment='币种'),
    sa.Column('given_at', sa.Date(), nullable=True, comment='送出/收到日期'),
    sa.Column('link', sa.String(length=500), nullable=True, comment='购买/参考链接'),
    sa.Column('description', sa.Text(), nullable=True, comment='说明（Markdown）'),
    *_D7_COLUMNS, *_TIMESTAMPS,
    *_D7_CONSTRAINTS,
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gifts_contact_id'), 'gifts', ['contact_id'], unique=False)
    op.create_index(op.f('ix_gifts_family_id'), 'gifts', ['family_id'], unique=False)
    op.create_index(op.f('ix_gifts_owner_user_id'), 'gifts', ['owner_user_id'], unique=False)

    # 3) 愿望清单（converted_gift_id 回链礼物）
    op.create_table('wishlist_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('contact_id', sa.BigInteger(), nullable=True, comment='为谁准备'),
    sa.Column('title', sa.String(length=200), nullable=False, comment='想送的礼物'),
    sa.Column('amount', sa.Numeric(12, 2), nullable=True, comment='预算/价格'),
    sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False, comment='币种'),
    sa.Column('link', sa.String(length=500), nullable=True, comment='购买链接'),
    sa.Column('description', sa.Text(), nullable=True, comment='说明（Markdown）'),
    sa.Column('status', sa.Enum('open', 'purchased', 'given', name='wishlist_status_enum'), server_default='open', nullable=False, comment='open 想送 / purchased 已购买 / given 已送出'),
    sa.Column('target_date', sa.Date(), nullable=True, comment='打算送出的日期（如对方生日）'),
    sa.Column('converted_gift_id', sa.BigInteger(), nullable=True, comment='转成礼物记录后的回链'),
    *_D7_COLUMNS, *_TIMESTAMPS,
    *_D7_CONSTRAINTS,
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
    sa.ForeignKeyConstraint(['converted_gift_id'], ['gifts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_wishlist_items_contact_id'), 'wishlist_items', ['contact_id'], unique=False)
    op.create_index(op.f('ix_wishlist_items_family_id'), 'wishlist_items', ['family_id'], unique=False)
    op.create_index(op.f('ix_wishlist_items_owner_user_id'), 'wishlist_items', ['owner_user_id'], unique=False)

    # 4) 资金往来（due_at 未结清 = 主页还款提醒源）
    op.create_table('fund_flows',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('contact_id', sa.BigInteger(), nullable=True, comment='对象联系人'),
    sa.Column('direction', sa.Enum('out', 'in', name='fund_direction_enum'), nullable=False, comment='out 流出（借出/支出） / in 流入（借入/收到）'),
    sa.Column('category', sa.Enum('loan', 'repayment', 'gift_money', 'other', name='fund_category_enum'), nullable=False, comment='loan 借款 / repayment 还款 / gift_money 礼金 / other 其他'),
    sa.Column('amount', sa.Numeric(12, 2), nullable=False, comment='金额'),
    sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False, comment='币种'),
    sa.Column('occurred_at', sa.Date(), nullable=False, comment='发生日'),
    sa.Column('due_at', sa.Date(), nullable=True, comment='应收/应还日'),
    sa.Column('status', sa.Enum('pending', 'settled', name='fund_status_enum'), nullable=True, comment='pending 未结清 / settled 已结清 / NULL 不涉及'),
    sa.Column('settled_at', sa.Date(), nullable=True, comment='结清日'),
    sa.Column('description', sa.Text(), nullable=True, comment='说明（Markdown）'),
    *_D7_COLUMNS, *_TIMESTAMPS,
    *_D7_CONSTRAINTS,
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fund_flows_contact_id'), 'fund_flows', ['contact_id'], unique=False)
    op.create_index(op.f('ix_fund_flows_family_id'), 'fund_flows', ['family_id'], unique=False)
    op.create_index(op.f('ix_fund_flows_owner_user_id'), 'fund_flows', ['owner_user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('fund_flows')
    op.drop_table('wishlist_items')
    op.drop_table('gifts')
    # 恢复单联系人列：每个活动取一个参与者（历史数据无法完全还原一对多前形态）
    op.add_column('activities', sa.Column('contact_id', sa.BigInteger(), nullable=True))
    op.create_index(op.f('ix_activities_contact_id'), 'activities', ['contact_id'], unique=False)
    op.execute(
        'UPDATE activities SET contact_id = p.contact_id '
        'FROM (SELECT DISTINCT ON (activity_id) activity_id, contact_id '
        '      FROM activity_participants ORDER BY activity_id, id) AS p '
        'WHERE activities.id = p.activity_id'
    )
    op.drop_index(op.f('ix_activity_participants_contact_id'), table_name='activity_participants')
    op.drop_index(op.f('ix_activity_participants_activity_id'), table_name='activity_participants')
    op.drop_table('activity_participants')
