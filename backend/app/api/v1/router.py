"""API v1 路由注册表：新业务模块在此一行挂载（ROADMAP 扩展性约定 2）。"""

from fastapi import APIRouter

from app.modules.ai.api import router as ai_router
from app.modules.auth.api import router as auth_router
from app.modules.contacts.api import router as contacts_router
from app.modules.dashboard.api import router as dashboard_router
from app.modules.dashboard.api import timeline_router as dashboard_timeline_router
from app.modules.funds.api import router as funds_router
from app.modules.gifts.api import router as gifts_router
from app.modules.graph.api import router as graph_router
from app.modules.records.api import router as records_router
from app.modules.settings.api import router as settings_router
from app.modules.uploads.api import router as uploads_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(contacts_router)
api_v1_router.include_router(dashboard_timeline_router)
api_v1_router.include_router(records_router)
api_v1_router.include_router(gifts_router)
api_v1_router.include_router(funds_router)
api_v1_router.include_router(graph_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(uploads_router)
api_v1_router.include_router(ai_router)


@api_v1_router.get("/health", tags=["meta"])
async def health() -> dict:
    """健康检查：compose 健康探测与冒烟测试使用。"""
    return {"status": "ok"}
