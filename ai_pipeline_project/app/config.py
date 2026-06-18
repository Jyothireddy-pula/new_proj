from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_ASYNC_URL: str = "postgresql+asyncpg://postgres@db:5432/transactions"
    REDIS_URL: str = "redis://redis:6373/0"
    GEMINI_API_KEY: str = ""
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=(".env", "ai_pipeline_project/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
