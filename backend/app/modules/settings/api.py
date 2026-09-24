"""settings 模块 API：AI 配置读写与连接测试（配置页数据源，D6.2）。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.modules.ai.embedding import build_embedder, load_embedding_config
from app.modules.ai.llm import build_chat_model, load_llm_config
from app.modules.auth.models import User
from app.modules.settings.service import (
    KEY_AI_EMBEDDING,
    KEY_AI_LLM,
    KEY_GEO_AMAP,
    get_setting_value,
    set_setting_value,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class AiStatusOut(BaseModel):
    """AI 能力可用性状态：前端据此决定是否引导用户去配置。"""

    configured: bool
    provider: str | None = None


class AiLlmConfigOut(BaseModel):
    """LLM 配置回显：api_key 只回显掩码，明文不出后端。"""

    configured: bool = True
    base_url: str
    model: str
    api_key_masked: str
    temperature: float = 0.0


class AiLlmConfigIn(BaseModel):
    """LLM 配置保存请求。"""

    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class AiTestOut(BaseModel):
    """连接测试结果：真实发一次最小补全验证连通性与密钥。"""

    ok: bool
    message: str


@router.get("/ai-status", response_model=AiStatusOut)
async def read_ai_status(db: AsyncSession = Depends(get_db)) -> AiStatusOut:
    """返回 LLM 是否已配置（D6.2 降级契约的数据源）。"""
    llm_config = await get_setting_value(db, KEY_AI_LLM)
    if not llm_config:
        return AiStatusOut(configured=False)
    return AiStatusOut(configured=True, provider=llm_config.get("provider"))


@router.get("/ai", response_model=AiLlmConfigOut | AiStatusOut)
async def read_ai_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取 LLM 配置（未配置返回 configured=false 形态）。"""
    config = await load_llm_config(db)
    if config is None:
        return AiStatusOut(configured=False)
    api_key = str(config["api_key"])
    masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
    return AiLlmConfigOut(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        api_key_masked=masked,
        temperature=float(config.get("temperature", 0.0)),
    )


@router.put("/ai", response_model=AiStatusOut)
async def save_ai_config(
    body: AiLlmConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiStatusOut:
    """保存 LLM 配置（家庭可信环境：登录用户均可维护，记录修改人）。"""
    await set_setting_value(
        db,
        KEY_AI_LLM,
        body.model_dump(),
        updated_by=current_user.id,
    )
    return AiStatusOut(configured=True, provider="openai-compatible")


@router.post("/ai/test", response_model=AiTestOut)
async def test_ai_connection(
    body: AiLlmConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiTestOut:
    """用提交的配置真实发一次最小补全（不落库），验证端点与密钥可用。"""
    try:
        model = build_chat_model(body.model_dump())
        await model.ainvoke("回复：连接成功")
        return AiTestOut(ok=True, message="连接成功")
    except Exception as exc:  # noqa: BLE001 连接失败原因透传给配置页
        return AiTestOut(ok=False, message=f"连接失败：{exc}")


class AiEmbeddingConfigOut(BaseModel):
    """Embedding 配置回显（api_key 掩码）。"""

    configured: bool = True
    base_url: str
    model: str
    api_key_masked: str


class AiEmbeddingConfigIn(BaseModel):
    """Embedding 配置保存请求（维度固定 1024，见 D6.3）。"""

    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)


@router.get("/embedding", response_model=AiEmbeddingConfigOut | AiStatusOut)
async def read_embedding_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取 Embedding 配置（未配置返回 configured=false 形态）。"""
    config = await load_embedding_config(db)
    if config is None:
        return AiStatusOut(configured=False)
    api_key = str(config["api_key"])
    masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
    return AiEmbeddingConfigOut(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        api_key_masked=masked,
    )


@router.put("/embedding", response_model=AiStatusOut)
async def save_embedding_config(
    body: AiEmbeddingConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiStatusOut:
    """保存 Embedding 配置（保存后需在 AI 页重建语义索引）。"""
    await set_setting_value(
        db, KEY_AI_EMBEDDING, body.model_dump(), updated_by=current_user.id
    )
    return AiStatusOut(configured=True, provider="openai-compatible")


@router.post("/embedding/test", response_model=AiTestOut)
async def test_embedding_connection(
    body: AiEmbeddingConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiTestOut:
    """测试 Embedding 连接（真实向量化一条短文本并校验维度）。"""
    try:
        embedder = build_embedder(body.model_dump())
        vectors = await embedder(["连接测试"])
        dim = len(vectors[0])
        return AiTestOut(ok=True, message=f"连接成功（返回维度 {dim}）")
    except Exception as exc:  # noqa: BLE001 失败原因透传配置页
        return AiTestOut(ok=False, message=f"连接失败：{exc}")


class GeoAmapConfigOut(BaseModel):
    """高德 key 回显（掩码）。"""

    configured: bool = True
    api_key_masked: str


class GeoAmapConfigIn(BaseModel):
    """高德 key 保存请求（Web 服务类型 key，用于地理编码）。"""

    api_key: str = Field(min_length=1)


@router.get("/geo/amap", response_model=GeoAmapConfigOut | AiStatusOut)
async def read_amap_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取高德 key 配置（未配置返回 configured=false 形态）。"""
    config = await get_setting_value(db, KEY_GEO_AMAP)
    if not config or not config.get("api_key"):
        return AiStatusOut(configured=False)
    api_key = str(config["api_key"])
    masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
    return GeoAmapConfigOut(api_key_masked=masked)


@router.put("/geo/amap", response_model=AiStatusOut)
async def save_amap_config(
    body: GeoAmapConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiStatusOut:
    """保存高德 key；保存后联系人位置解析走高德，未配置走静态表（D14）。"""
    await set_setting_value(
        db, KEY_GEO_AMAP, {"api_key": body.api_key}, updated_by=current_user.id
    )
    return AiStatusOut(configured=True, provider="amap")


@router.post("/geo/amap/test", response_model=AiTestOut)
async def test_amap_connection(
    body: GeoAmapConfigIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiTestOut:
    """测试高德 key：真实解析一次固定地址，验证 key 有效性与配额。"""
    from app.modules.geo.amap import resolve_amap

    try:
        result = await resolve_amap("北京市", body.api_key)
        if result is None:
            return AiTestOut(ok=False, message="key 可连通但未解析到结果，请确认为 Web 服务类型")
        coord = f"{result.lng:.4f}, {result.lat:.4f}"
        return AiTestOut(ok=True, message=f"连接成功（解析北京市：{coord}）")
    except Exception as exc:  # noqa: BLE001 失败原因透传配置页
        return AiTestOut(ok=False, message=f"连接失败：{exc}")
