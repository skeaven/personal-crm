"""ai 模块 /mcp 端点：工具注册表的 MCP Streamable HTTP 出口（D11）。

- 工具单一实现源：registry.ALL_TOOLS 动态注册为 MCP 工具，与内部 agent 同源；
- 鉴权：复用用户 JWT（个人访问令牌签发 UI 后补，ARCHITECTURE 已注明过渡态）；
  JWT 在 ASGI 门卫层解析并写入 contextvar，工具执行以该用户身份进行（D7）；
- 每次工具调用独立开数据库会话（不依赖 FastAPI 请求作用域）。
"""

import contextvars
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer
from starlette.responses import JSONResponse

from app.core.security import decode_access_token
from app.modules.ai import registry
from app.modules.ai.registry import build_args

# MCP 请求作用域的当前用户（由 JWT 门卫层写入）
mcp_current_user: contextvars.ContextVar = contextvars.ContextVar("mcp_current_user", default=None)

mcp_server = MCPServer("personal-crm")


def _dynamic_handler(ai_tool):
    """按工具 schema 动态构造平铺签名函数（MCPServer 由签名生成 JSON Schema）。"""
    parameters = []
    for name, field in ai_tool.args_schema.model_fields.items():
        if field.is_required():
            parameters.append(
                inspect.Parameter(
                    name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=field.annotation
                )
            )
        else:
            parameters.append(
                inspect.Parameter(
                    name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=field.annotation,
                    default=field.default,
                )
            )

    async def handler(**kwargs):
        user = mcp_current_user.get()
        if user is None:
            return "错误：未认证"
        from app.core.db import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            tool_args = build_args(ai_tool, kwargs)
            return await ai_tool.run(session, user, tool_args)

    handler.__signature__ = inspect.Signature(parameters)
    handler.__doc__ = ai_tool.description
    return handler


def _register_all() -> None:
    """把注册表全部工具注册进 MCP server（重复导入幂等：先清再挂）。"""
    for tool in registry.ALL_TOOLS:
        try:
            mcp_server.remove_tool(tool.name)
        except Exception:  # noqa: BLE001 首次注册不存在属正常
            pass
        mcp_server.add_tool(
            _dynamic_handler(tool), name=tool.name, description=tool.description
        )


_register_all()


class JwtGate:
    """ASGI 门卫：校验 Bearer JWT，把用户写入 contextvar 后放行 MCP 子应用。"""

    def __init__(self, asgi_app) -> None:
        """包住 streamable http 子应用。"""
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send) -> None:
        """非 HTTP 请求直接放行；HTTP 请求必须携带有效 JWT。"""
        if scope["type"] != "http":
            await self.asgi_app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode()
        token = auth.removeprefix("Bearer ").strip()
        if not token:
            response = JSONResponse(
                {"message": "缺少访问令牌"}, status_code=401
            )
            await response(scope, receive, send)
            return

        from app.core.db import get_session_factory
        from app.modules.auth.models import User

        try:
            user_id = decode_access_token(token)
        except Exception:  # noqa: BLE001 令牌无效/过期一律 401
            user_id = None
        user = None
        if user_id is not None:
            factory = get_session_factory()
            async with factory() as session:
                user = await session.get(User, user_id)

        if user is None:
            response = JSONResponse({"message": "访问令牌无效"}, status_code=401)
            await response(scope, receive, send)
            return

        mcp_current_user.set(user)
        await self.asgi_app(scope, receive, send)


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """宿主应用 lifespan 内启动 MCP 会话管理器（SDK 要求，仅可运行一次）。"""
    async with mcp_server.session_manager.run():
        yield


def get_mcp_asgi_app():
    """返回带 JWT 门卫的 Streamable HTTP 子应用（main.py 挂载到 /mcp）。"""
    return JwtGate(mcp_server.streamable_http_app())
