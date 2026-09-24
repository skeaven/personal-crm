"""业务异常体系：service 层抛出，api 层统一转换为 HTTP 状态码。"""


class BusinessError(Exception):
    """业务错误基类；message 面向用户可读。"""

    status_code = 400

    def __init__(self, message: str):
        """记录用户可读的错误信息。"""
        super().__init__(message)
        self.message = message


class PermissionDeniedError(BusinessError):
    """D7 权限拒绝：非所有者尝试写入。"""

    status_code = 403


class NotFoundError(BusinessError):
    """资源不存在或对当前用户不可见。"""

    status_code = 404


class UnauthorizedError(BusinessError):
    """未登录或凭证失效。"""

    status_code = 401


class ValidationError(BusinessError):
    """业务规则校验失败（区别于 Pydantic 的 422 契约错误，语义同为不可受理）。"""

    status_code = 422


class ConflictError(BusinessError):
    """资源状态冲突（如重复创建同一实体）。"""

    status_code = 409
