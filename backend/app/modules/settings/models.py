"""settings 模块 ORM 模型：AppSetting 键值配置。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppSetting(Base):
    """运行时配置键值对：LLM/Embedding 等在配置页修改，改完即生效（无需重启）。"""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, comment="配置键，如 ai.llm"
    )
    value: Mapped[dict] = mapped_column(JSONB, comment="结构化配置值")
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True, comment="最后修改人"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
