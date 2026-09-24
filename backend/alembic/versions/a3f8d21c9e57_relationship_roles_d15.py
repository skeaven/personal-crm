"""关系角色化（D15）：roles/status/is_system/kind + users.contact_id + 存量角色映射

存量映射原则：只填角色与系统类型，不翻转边方向（视角解析两端皆可）；
隔代压缩标签（爷爷/舅舅等）无法单边表达，role 留空走兼容句式。

Revision ID: a3f8d21c9e57
Revises: f2a9c4b81e63
Create Date: 2026-09-22

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f8d21c9e57'
down_revision: str | None = 'f2a9c4b81e63'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (标签, 系统类型 kind, from_role, to_role 按 to 端性别: male/female)
_ROLE_MIGRATIONS = [
    ("丈夫", "spouse", "husband", ("wife", "wife")),
    ("父亲", "parent", "father", ("son", "daughter")),
    ("母亲", "parent", "mother", ("son", "daughter")),
    ("儿子", "parent", "son", ("father", "mother")),
    ("女儿", "parent", "daughter", ("father", "mother")),
    ("哥哥", "sibling", "elder_brother", ("younger_brother", "younger_sister")),
    ("姐姐", "sibling", "elder_sister", ("younger_brother", "younger_sister")),
]


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        'relationship_types',
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false'),
                  comment='系统结构化类型（可参与称谓推导）'),
    )
    op.add_column(
        'relationship_types',
        sa.Column('kind', sa.String(length=20), nullable=True, comment='结构类别：parent/spouse/sibling'),
    )
    op.add_column(
        'relationships',
        sa.Column('from_role', sa.String(length=30), nullable=True, comment='from 是 to 的角色'),
    )
    op.add_column(
        'relationships',
        sa.Column('to_role', sa.String(length=30), nullable=True, comment='to 是 from 的角色'),
    )
    op.add_column(
        'relationships',
        sa.Column('status', sa.String(length=10), nullable=False, server_default='active',
                  comment='active / former'),
    )
    op.add_column(
        'users',
        sa.Column('contact_id', sa.BigInteger(), nullable=True, comment='"我"绑定的联系人（D15 视角起点）'),
    )
    op.create_foreign_key('fk_users_contact', 'users', 'contacts', ['contact_id'], ['id'])
    op.create_unique_constraint('uq_users_contact', 'users', ['contact_id'])

    # 系统类型三行（幂等）：结构化角色关系由这三类表达
    for kind, name in (("spouse", "配偶"), ("parent", "父母-子女"), ("sibling", "兄弟姐妹")):
        bind.execute(sa.text(
            "INSERT INTO relationship_types (group_name, name, reverse_name, sort_order, is_system, kind, created_at, updated_at)"
            " SELECT 'family', CAST(:name AS varchar), NULL, 0, true, CAST(:kind AS varchar), now(), now()"
            " WHERE NOT EXISTS (SELECT 1 FROM relationship_types WHERE kind = CAST(:kind AS varchar) AND is_system)"
        ), {"name": name, "kind": kind})

    # 存量边映射：按旧正向标签换系统类型并填角色（to_role 依 to 端性别；不翻转方向）
    for label, kind, from_role, (to_male, to_female) in _ROLE_MIGRATIONS:
        bind.execute(sa.text(
            "UPDATE relationships r SET type_id = sys.id, from_role = :from_role,"
            " to_role = CASE WHEN c.gender = 'male' THEN :to_male"
            " WHEN c.gender = 'female' THEN :to_female ELSE NULL END"
            " FROM relationship_types old_t, relationship_types sys, contacts c"
            " WHERE r.type_id = old_t.id AND old_t.name = :label AND old_t.is_system = false"
            " AND sys.kind = :kind AND sys.is_system AND c.id = r.to_contact_id"
        ), {"label": label, "kind": kind, "from_role": from_role, "to_male": to_male, "to_female": to_female})


def downgrade() -> None:
    bind = op.get_bind()
    # 角色化边退回旧标签不可逆（信息已融合），仅删除系统类型行与结构
    bind.execute(sa.text("DELETE FROM relationship_types WHERE is_system"))
    op.drop_constraint('uq_users_contact', 'users', type_='unique')
    op.drop_constraint('fk_users_contact', 'users', type_='foreignkey')
    op.drop_column('users', 'contact_id')
    op.drop_column('relationships', 'status')
    op.drop_column('relationships', 'to_role')
    op.drop_column('relationships', 'from_role')
    op.drop_column('relationship_types', 'kind')
    op.drop_column('relationship_types', 'is_system')
