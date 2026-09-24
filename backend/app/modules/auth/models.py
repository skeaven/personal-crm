"""auth 模块 ORM 模型：Family / User / UserToken。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import TimestampMixin


class Family(Base, TimestampMixin):
    """家庭组：D7 权限的共享边界，邀请/移除即全部，不做多层组织。"""

    __tablename__ = "families"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), comment="家庭名称")


class User(Base, TimestampMixin):
    """家庭成员账号；family_id 决定其共享读取范围。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("families.id"), index=True, comment="所属家庭"
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, comment="登录名，小写存储"
    )
    display_name: Mapped[str] = mapped_column(String(50), comment="展示名")
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希（bcrypt）")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", comment="停用开关"
    )
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        # use_alter：users↔contacts 互相 FK 成环，建表时延迟为 ALTER 语句创建
        ForeignKey("contacts.id", use_alter=True, name="fk_users_contact"),
        unique=True,
        nullable=True,
        comment="\"我\"绑定的联系人（D15 视角推导起点）",
    )

    family: Mapped[Family] = relationship(lazy="joined")


class UserToken(Base, TimestampMixin):
    """外部客户端访问令牌（D11）：MCP 客户端以对应用户身份操作，仅存哈希。"""

    __tablename__ = "user_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), comment="令牌用途，如 Claude Desktop")
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, comment="令牌哈希")
    scopes: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", comment="权限范围，预留"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
