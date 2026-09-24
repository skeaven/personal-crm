"""应用入口：应用工厂 + MCP 端点 + 生产模式 SPA 静态托管（D2 一体化部署）。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import BusinessError

# 仓库根目录下的前端构建产物（backend/app/main.py → 上三级为仓库根）
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def _register_exception_handlers(app: FastAPI) -> None:
    """把业务异常统一转换为 {message} JSON，HTTP 状态码由异常类决定。"""

    async def business_error_handler(_: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"message": exc.message})

    app.add_exception_handler(BusinessError, business_error_handler)


class _ImmutableStatic(StaticFiles):
    """带一年缓存头的静态文件挂载（Vite 产物文件名含内容哈希）。"""

    def file_response(self, *args, **kwargs) -> FileResponse:
        """在默认文件响应上追加 Cache-Control。"""
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _mount_frontend(app: FastAPI) -> None:
    """存在前端构建产物时接管非 /api 路径：静态文件优先，其余回退 index.html。"""
    if not _FRONTEND_DIST.is_dir():
        return
    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", _ImmutableStatic(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """SPA 回退：命不中静态文件时返回 index.html，交由前端路由接管。"""
        dist_root = _FRONTEND_DIST.resolve()
        candidate = (dist_root / full_path).resolve()
        if candidate.is_file() and str(candidate).startswith(str(dist_root)):
            return FileResponse(candidate)
        return FileResponse(dist_root / "index.html")


def create_app() -> FastAPI:
    """组装 FastAPI 应用：路由注册、MCP 端点、异常处理、静态托管。"""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """宿主生命周期：承载 MCP 会话管理器（SDK 要求挂载前调用 streamable app）。"""
        from app.modules.ai.mcp_endpoint import mcp_lifespan

        async with mcp_lifespan():
            yield

    application = FastAPI(title=get_settings().app_name, lifespan=lifespan)
    application.include_router(api_v1_router, prefix="/api/v1")

    # MCP Streamable HTTP 出口（D11）：挂在 /mcp 前缀，JWT 门卫在子应用内
    from app.modules.ai.mcp_endpoint import get_mcp_asgi_app

    application.mount("/mcp", get_mcp_asgi_app(), name="mcp")

    _register_exception_handlers(application)
    _mount_frontend(application)
    return application


app = create_app()
