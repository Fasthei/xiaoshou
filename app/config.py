from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "销售系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 数据库
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # 本地 JWT（开发/退化）
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Casdoor
    AUTH_ENABLED: bool = True
    CASDOOR_ENDPOINT: str = ""
    CASDOOR_CLIENT_ID: str = ""
    CASDOOR_CLIENT_SECRET: str = ""
    CASDOOR_ORG: str = "built-in"
    CASDOOR_APP_NAME: str = "xiaoshou"
    CASDOOR_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback"
    CASDOOR_CERT: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings():
    return Settings()
