"""ai 模块 API：对话流（SSE）、写入提议确认、工具清单。

chat 的聚合实现依赖 backend/agent/runner（deepagents 唯一封装点）。
"""

import base64
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import BusinessError, NotFoundError, ValidationError
from app.modules.ai import pending as pending_service
from app.modules.ai import registry, semantic, sessions
from app.modules.ai.llm import LLMNotConfiguredError, require_llm
from app.modules.auth.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatIn(BaseModel):
    """对话请求：session_id 由前端生成（一个对话一个 id）；images 为临时区图片路径，最多 1 张。"""

    message: str = Field(min_length=1)
    session_id: str | None = None
    images: list[str] | None = Field(default=None, max_length=1)


class PendingActionOut(BaseModel):
    """写入提议（确认队列条目）。"""

    id: int
    tool_name: str
    payload: dict
    preview: dict | None = None
    status: str
    result: dict | None = None
    created_at: str


class ToolOut(BaseModel):
    """MCP 工具清单条目（对外暴露的能力声明）。"""

    name: str
    label: str
    description: str
    risk: str


class AiSessionOut(BaseModel):
    """会话索引输出。"""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class HistoryMessageOut(BaseModel):
    """历史消息：与流式事件的渲染形状一致，前端可复用同一套渲染。"""

    role: str
    content: str
    tools: list[str] = []


def _sse(event: dict) -> str:
    """编码一条 SSE data 帧（中文不转义，前端 JSON.parse 直接用）。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _load_image_data_uris(user: User, images: list[str] | None) -> list[str]:
    """校验并读取请求附图，返回 data URI 列表（直接可喂给视觉模型）。

    两道关：路径必须解析到**本人临时区**内（storage.resolve_own_temp，同时
    覆盖前缀归属与 ../ 穿越）、文件必须存在；任一不过一律 404。校验发生在
    SSE 响应开始之前——流一开始状态码就改不了了。
    """
    from app.services import storage

    uris: list[str] = []
    for temp_path in images or []:
        try:
            path = storage.resolve_own_temp(temp_path, user.id)
        except ValidationError as exc:
            # 前缀像本人的、解析后却不是（../ 穿越到他人临时区或正式区）：
            # 一律按「不存在」回应，既不泄露路径规则也不泄露他人文件是否存在。
            raise NotFoundError("图片不存在") from exc
        if not path.is_file():
            raise NotFoundError("图片不存在或已过期，请重新上传")
        encoded = base64.b64encode(path.read_bytes()).decode()
        uris.append(f"data:{storage.image_mime(path.suffix)};base64,{encoded}")
    return uris


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(current_user: User = Depends(get_current_user)) -> list[ToolOut]:
    """工具清单（D11：内外共用同一份注册表）。"""
    return [
        ToolOut(name=tool.name, label=tool.label, description=tool.description, risk=tool.risk)
        for tool in registry.ALL_TOOLS
    ]


@router.post("/chat")
async def chat(
    body: ChatIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """agent 对话（SSE 流）：文本增量 / 工具调用状态 / 写入提议 / 错误 / 结束帧。"""
    # 图片校验必须在构造 StreamingResponse 之前：SSE 一旦开始，404 这类
    # 状态码就发不出去了，只能以 JSON 错误响应提前拒绝。
    image_uris = _load_image_data_uris(current_user, body.images)

    async def event_stream():
        session_id = body.session_id or str(uuid.uuid4())
        try:
            # 首轮提问顺手建索引行；已存在则只更新活跃时间。
            # 主键撞车（属于他人）会抛 NotFoundError，一并走下面的错误帧。
            await sessions.ensure_session(db, current_user, session_id, body.message)
            yield _sse({"type": "start", "session_id": session_id})
            llm = await require_llm(db)
            from agent.runner import stream_agent

            async for event in stream_agent(
                db, current_user, llm, body.message, session_id, image_uris
            ):
                yield _sse(event)
        except LLMNotConfiguredError as exc:
            yield _sse({"type": "error", "code": "llm_not_configured", "message": exc.message})
        except BusinessError as exc:
            yield _sse({"type": "error", "message": exc.message})
        except Exception:  # 业务外异常（上游 500 等）也要喂给前端，否则流静默断开
            yield _sse({"type": "error", "message": "对话处理失败，请稍后重试"})
        finally:
            yield _sse({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions", response_model=list[AiSessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AiSessionOut]:
    """我的会话列表（按最后活跃倒序）。"""
    return await sessions.list_sessions(db, current_user)


@router.get("/sessions/{session_id}/messages", response_model=list[HistoryMessageOut])
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HistoryMessageOut]:
    """某会话的历史消息；不属于当前用户按 404 处理。"""
    return await sessions.get_history(db, current_user, session_id)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除会话：索引行与 checkpointer 数据一并清掉。"""
    from agent.runner import delete_history

    await sessions.get_owned_session(db, current_user, session_id)
    await delete_history(session_id, current_user.id)
    await sessions.delete_session(db, current_user, session_id)
    return Response(status_code=204)


class RebuildOut(BaseModel):
    """重建索引结果统计。"""

    embedded: int
    skipped: int
    removed: int


class SearchItemOut(BaseModel):
    """语义搜索结果条目。"""

    entity_type: str
    entity_id: int
    content: str
    distance: float


@router.post("/embeddings/rebuild", response_model=RebuildOut)
async def rebuild_embeddings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RebuildOut:
    """全量对账重建语义索引：新增/变更重算、消失清理（幂等）。"""
    summary = await semantic.rebuild_index(db, current_user)
    return RebuildOut(**summary)


@router.get("/search", response_model=list[SearchItemOut])
async def semantic_search(
    q: str = Query(min_length=1),
    limit: int = Query(default=8, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SearchItemOut]:
    """语义搜索（按含义检索联系人/活动/礼物/资金/备注）。"""
    results = await semantic.search(db, current_user, q, limit=limit)
    return [SearchItemOut(**item) for item in results]


@router.get("/pending", response_model=list[PendingActionOut])
async def list_pending(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PendingActionOut]:
    """我的待确认写入提议。"""
    actions = await pending_service.list_pending(db, current_user)
    return [PendingActionOut(**pending_service.to_dict(action)) for action in actions]


@router.post("/pending/{action_id}/approve", response_model=PendingActionOut)
async def approve_pending(
    action_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PendingActionOut:
    """确认提议并执行（以提议人身份落库，失败原因记入 result）。"""
    action = await pending_service.approve(db, current_user, action_id)
    return PendingActionOut(**pending_service.to_dict(action))


@router.post("/pending/{action_id}/reject", response_model=PendingActionOut)
async def reject_pending(
    action_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PendingActionOut:
    """拒绝提议。"""
    action = await pending_service.reject(db, current_user, action_id)
    return PendingActionOut(**pending_service.to_dict(action))
