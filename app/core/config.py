"""Application-wide configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application ---
    PROJECT_NAME: str = "Hyper-Local Logistics & Marketplace API"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: list[str] = Field(default_factory=list)

    # --- Database ---
    DATABASE_URL: PostgresDsn
    SYNC_DATABASE_URL: PostgresDsn | None = None

    POSTGRES_USER: str = "marketplace"
    POSTGRES_PASSWORD: str = "marketplace"
    POSTGRES_DB: str = "marketplace"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True
    DB_ECHO: bool = False

    # --- Redis ---
    REDIS_URL: RedisDsn = Field(default="redis://localhost:6379/0")

    # --- Security ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.startswith("["):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def sync_database_uri(self) -> str:
        """Synchronous (psycopg2) database URI used by Alembic."""
        if self.SYNC_DATABASE_URL is not None:
            return str(self.SYNC_DATABASE_URL)
        return str(self.DATABASE_URL).replace("+asyncpg", "+psycopg2")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
