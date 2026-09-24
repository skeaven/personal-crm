"""ai 模块 LLM 客户端工厂：运行时读取 app_settings 构建 ChatOpenAI（D6.2）。

配置键 settings.KEY_AI_LLM，value 形状：
{"provider": "openai-compatible", "base_url": "...", "api_key": "...", "model": "..."}
未配置时系统其余功能完全可用，任何 AI 调用抛 LLMNotConfiguredError 引导配置。
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError
from app.modules.settings.service import KEY_AI_LLM, get_setting_value


class LLMNotConfiguredError(BusinessError):
    """LLM 尚未配置（D6.2 降级契约：明确报错并引导去配置页）。"""

    status_code = 400

    def __init__(self) -> None:
        """固定提示语，前端据此跳转设置页。"""
        super().__init__("尚未配置 LLM，请先在设置页完成配置")


async def load_llm_config(db: AsyncSession) -> dict | None:
    """读取 LLM 配置；键不存在或字段不完整视为未配置。"""
    config = await get_setting_value(db, KEY_AI_LLM)
    if not config:
        return None
    required = ("base_url", "api_key", "model")
    if any(not str(config.get(field) or "").strip() for field in required):
        return None
    return config


async def require_llm(db: AsyncSession) -> BaseChatModel:
    """取当前 LLM 客户端；未配置抛 LLMNotConfiguredError。"""
    config = await load_llm_config(db)
    if config is None:
        raise LLMNotConfiguredError()
    return build_chat_model(config)


def build_chat_model(config: dict) -> BaseChatModel:
    """按配置构建 OpenAI 兼容客户端（国产模型/自建网关均走此形态）。"""
    return ChatOpenAI(
        api_key=str(config["api_key"]),
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        temperature=float(config.get("temperature", 0.0)),
        timeout=60,
    )
