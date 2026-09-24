"""auth 模块 Pydantic 模式：登录请求与用户信息输出。"""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """用户信息输出（不含密码等敏感字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    family_id: int
    contact_id: int | None = None


class MeUpdate(BaseModel):
    """更新当前用户：绑定"我是谁"（联系人节点，D15 视角推导起点）。"""

    contact_id: int | None = Field(default=None, description="绑定的联系人；null=解绑")


class LoginResponse(BaseModel):
    """登录成功响应：令牌 + 用户信息。"""

    access_token: str
    token_type: str = "bearer"
    user: UserOut
