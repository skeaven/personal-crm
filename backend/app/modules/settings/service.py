"""settings 模块服务层：配置读写，供配置 API 与 AI 模块（Level 4）复用。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import AppSetting

# 已知配置键常量集中定义，避免魔法字符串散落
KEY_AI_LLM = "ai.llm"
KEY_AI_EMBEDDING = "ai.embedding"
KEY_GEO_AMAP = "geo.amap"


async def get_setting_value(db: AsyncSession, key: str) -> dict | None:
    """读取配置值；键不存在返回 None。"""
    stmt = select(AppSetting).where(AppSetting.key == key)
    record = (await db.execute(stmt)).scalar_one_or_none()
    return record.value if record else None


async def set_setting_value(
    db: AsyncSession, key: str, value: dict, updated_by: int | None
) -> None:
    """写入配置值（存在则覆盖）；由调用方决定提交时机（请求级事务）。"""
    stmt = select(AppSetting).where(AppSetting.key == key)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if record is None:
        record = AppSetting(key=key, value=value, updated_by=updated_by)
        db.add(record)
    else:
        record.value = value
        record.updated_by = updated_by
    await db.flush()
