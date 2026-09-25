"""应用配置：进程级环境差异走环境变量/.env；业务运行时配置走 app_settings 表（D6.2）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """进程级配置项。字段均可被同名环境变量覆盖。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Personal CRM"
    debug: bool = True
    # 异步 PostgreSQL 连接串（D3：单库承载结构化数据；向量表 Level 4 迁移再加入）
    database_url: str = "postgresql+asyncpg://crm:crm@127.0.0.1:5433/personal_crm"
    # JWT 签名密钥：生产部署必须通过环境变量注入强随机值
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    # 登录态有效期（分钟），家庭自托管场景给长会话
    jwt_expire_minutes: int = 60 * 24 * 7

    # 上传文件根目录（D18）：开发环境为 backend/uploads，容器内由 env 指向挂载卷
    upload_dir: str = "uploads"


@lru_cache
def get_settings() -> Settings:
    """返回配置单例；lru_cache 保证全进程只读一次环境。"""
    return Settings()
