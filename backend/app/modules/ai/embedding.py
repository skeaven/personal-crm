"""ai 模块 Embedding provider（D6.3）：线上优先，预留本地切换。

配置键 settings.KEY_AI_EMBEDDING，value 形状：
{"provider": "openai-compatible", "base_url": "...", "api_key": "...", "model": "..."}
输出维度固定 EMBEDDING_DIM（1024）：OpenAI text-embedding-3 用 dimensions 截断、
智谱 embedding-3 传 dims=1024、本地 bge-m3 原生 1024——换供应商不换维度，
因此 embeddings 表列无需迁移。本地切换=换 base_url/model（或后续本地 provider 类）。
"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BusinessError
from app.modules.ai.models import EMBEDDING_DIM
from app.modules.settings.service import KEY_AI_EMBEDDING, get_setting_value


class EmbeddingNotConfiguredError(BusinessError):
    """Embedding 尚未配置（降级契约：语义功能不可用，其余不受影响）。"""

    status_code = 400

    def __init__(self) -> None:
        """固定提示语，前端据此引导设置。"""
        super().__init__("尚未配置 Embedding 模型，请先在设置页完成配置")


async def load_embedding_config(db: AsyncSession) -> dict | None:
    """读取 Embedding 配置；键缺失或字段不完整视为未配置。"""
    config = await get_setting_value(db, KEY_AI_EMBEDDING)
    if not config:
        return None
    required = ("base_url", "api_key", "model")
    if any(not str(config.get(field) or "").strip() for field in required):
        return None
    return config


# embedder 统一形状：async (texts: list[str]) -> list[list[float]]
Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]


async def require_embedder(db: AsyncSession) -> tuple[dict, Embedder]:
    """取当前配置与 embedder 函数；未配置抛 EmbeddingNotConfiguredError。"""
    config = await load_embedding_config(db)
    if config is None:
        raise EmbeddingNotConfiguredError()
    return config, build_embedder(config)


def build_embedder(config: dict) -> Embedder:
    """构建 OpenAI 兼容 embedder：批量文本 → 1024 维向量列表。

    check_embedding_ctx_length=False：非 OpenAI 官方端点（国产网关）不做
    tiktoken 预分词截断，交由服务端处理（langchain 对兼容端点的标准建议）。
    """

    async def _embed(texts: list[str]) -> list[list[float]]:
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(
            api_key=str(config["api_key"]),
            base_url=str(config["base_url"]),
            model=str(config["model"]),
            dimensions=EMBEDDING_DIM,
            check_embedding_ctx_length=False,
        )
        return await embeddings.aembed_documents(texts)

    return _embed
