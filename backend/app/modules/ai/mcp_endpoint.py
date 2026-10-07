"""ai 模块 /mcp 端点：工具注册表的 MCP Streamable HTTP 出口（D11）。

- 工具单一实现源：registry.ALL_TOOLS 动态注册为 MCP 工具，与内部 agent 同源；
- 鉴权：JWT 与个人令牌（D11）并存——老客户端继续用 JWT，外部客户端用设置页
  签发的个人令牌；身份在 ASGI 门卫层解析并写入 contextvar，工具执行以该用户
  身份进行（D7）；
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
    """按工具 schema 动态构造平铺签名函数（MCPServer 由签名生成 JSON Schema）。

    inspect.Signature 要求无默认值参数必须排在带默认值参数之前，而 pydantic 模型
    对字段顺序没有这个限制。所以不能按 model_fields 原顺序直接铺：只要有「带默认
    值的字段在前、必填字段在后」的 schema（如 calendar 声明在 type/title 之后），
    构造 Signature 就会抛 ValueError，整个应用在 import 阶段就起不来。
    """
    required: list[inspect.Parameter] = []
    optional: list[inspect.Parameter] = []
    for name, field in ai_tool.args_schema.model_fields.items():
        if field.is_required():
            required.append(
                inspect.Parameter(
                    name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=field.annotation
                )
            )
        else:
            optional.append(
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
            result = await ai_tool.run(session, user, tool_args)
            # 服务层只 flush 不 commit（事务边界归调用方，见 core/db.py::get_db）。
            # REST 路径由 get_db 在 yield 后提交，MCP 路径没有那一层，必须在这里提交——
            # 否则会话退出即回滚，写工具回执说的"已生成提议（编号 N）"在库里根本不存在。
            await session.commit()
            return result

    handler.__signature__ = inspect.Signature([*required, *optional])
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


async def _reject(scope, receive, send, message: str) -> None:
    """统一的 401 响应；文案区分「没带」与「带了但无效」，便于客户端排查。"""
    await JSONResponse({"message": message}, status_code=401)(scope, receive, send)


async def _resolve_identity(token: str):
    """Bearer 令牌 → 用户：先按 JWT 解析，不通再按个人令牌解析；都不通返回 None。"""
    from app.core.db import get_session_factory
    from app.modules.auth import service as auth_service
    from app.modules.auth import tokens as token_service

    try:
        user_id = decode_access_token(token)
    except Exception:  # noqa: BLE001 JWT 无效/过期不是错误，继续试个人令牌
        user_id = None

    factory = get_session_factory()
    async with factory() as session:
        user = None
        if user_id is not None:
            user = await auth_service.get_user_by_id(session, user_id)
        if user is None:
            user = await token_service.resolve(session, token)
        if user is not None:
            # 门卫层自己开事务：get_db 的「一请求一事务」管不到 ASGI 中间件，
            # 不提交的话个人令牌的 last_used_at 刷新会随会话关闭被回滚。
            await session.commit()
        return user


class AuthGate:
    """ASGI 门卫：认 JWT 或个人令牌，把用户写入 contextvar 后放行 MCP 子应用。"""

    def __init__(self, asgi_app) -> None:
        """包住 streamable http 子应用。"""
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send) -> None:
        """非 HTTP 请求直接放行；HTTP 请求必须携带有效 JWT 或个人令牌。"""
        if scope["type"] != "http":
            await self.asgi_app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode()
        token = auth.removeprefix("Bearer ").strip()
        if not token:
            await _reject(scope, receive, send, "缺少访问令牌")
            return

        user = await _resolve_identity(token)
        if user is None:
            await _reject(scope, receive, send, "访问令牌无效")
            return

        mcp_current_user.set(user)
        await self.asgi_app(scope, receive, send)


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """宿主应用 lifespan 内启动 MCP 会话管理器（SDK 要求，仅可运行一次）。"""
    async with mcp_server.session_manager.run():
        yield


def get_mcp_asgi_app():
    """返回带鉴权门卫的 Streamable HTTP 子应用（main.py 挂载到 /mcp）。"""
    return AuthGate(mcp_server.streamable_http_app())
