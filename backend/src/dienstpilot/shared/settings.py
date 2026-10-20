"""Runtime configuration, read from the environment (and an optional .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Every value can be overridden by an environment variable."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dienstpilot:dienstpilot@localhost:5433/dienstpilot"
    redis_url: str = "redis://localhost:6379/0"
    llm_model_intake: str = "claude-haiku-5-5"
    llm_model_copilot: str = "claude-sonnet-5-5"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
