"""merge contact name fields d23

Revision ID: dfc278a66ffa
Revises: b8e9d4f3a276
Create Date: 2026-10-03

D23：姓名单字段化。last_name + first_name → name，并删除死字段 display_name_override。
"""

import sqlalchemy as sa
from alembic import op

revision = "dfc278a66ffa"
down_revision = "b8e9d4f3a276"
branch_labels = None
depends_on = None

# 先 trim 再拼：旧数据里姓/名任一首尾带空格时，直接拼接会得到「陈 建国」这种
# 内部带空格的姓名，展示与搜索都会失配。
_BACKFILL = (
    "UPDATE contacts SET name = "
    "trim(coalesce(last_name, '')) || trim(coalesce(first_name, ''))"
)


def upgrade() -> None:
    """加 name → 回填 → 删三列。顺序不可换，换了两列数据就没了。"""
    op.add_column(
        "contacts",
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
            server_default="",
            comment="姓名（中文姓名整体存储，D23）",
        ),
    )
    op.execute(_BACKFILL)
    # display_name_override 的用户数据在此丢弃：该字段前端从无填写入口，
    # 存量若有值（只可能来自直接调 API），这些联系人删列后展示名回退到 nickname > name。
    op.drop_column("contacts", "display_name_override")
    op.drop_column("contacts", "first_name")
    op.drop_column("contacts", "last_name")


def downgrade() -> None:
    """不可逆：整名无法可靠拆回姓/名（「陈建国」该拆成 陈+建国 还是 陈建+国？）。

    只还原列结构：整名整体存入 last_name（超 50 字符按 left(50) 截断，否则列宽不足报错），
    first_name 置空，display_name_override 保持 NULL。
    """
    op.add_column(
        "contacts",
        sa.Column(
            "last_name", sa.String(length=50), nullable=False, server_default="", comment="姓"
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "first_name", sa.String(length=50), nullable=False, server_default="", comment="名"
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "display_name_override",
            sa.String(length=100),
            nullable=True,
            comment="手动指定展示名，优先级最高",
        ),
    )
    op.execute("UPDATE contacts SET last_name = left(name, 50)")
    op.drop_column("contacts", "name")
