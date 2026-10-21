"""Runtime configuration, read from the environment (and an optional .env file)."""

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

TZ = ZoneInfo("Europe/Berlin")
# UI_SPEC §1: the demo moment, Tuesday 20 October 2026, 06:00 Europe/Berlin.
DEMO_NOW = datetime(2026, 10, 20, 6, 0, tzinfo=TZ)


class Settings(BaseSettings):
    """Application settings. Every value can be overridden by an environment variable."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dienstpilot:dienstpilot@localhost:5433/dienstpilot"
    redis_url: str = "redis://localhost:6379/0"
    llm_model_intake: str = "claude-haiku-5-5"
    llm_model_copilot: str = "claude-sonnet-5-5"
    # The instant the demo clock shows unless an Administrator moves it (DEMO_MODE only).
    demo_now: datetime = DEMO_NOW
    # Registers the demo endpoints (PUT /demo/clock). On in the dev stack, off otherwise.
    demo_mode: bool = False
    # Browser origins that may call the API, comma separated. Used only when DEMO_MODE is on
    # (Expo web in development and in the e2e run); without DEMO_MODE the API sends no CORS headers.
    cors_origins: str = "http://localhost:8081,http://localhost:8083"
    # Signs demo-login tokens. The default is for local development only.
    token_secret: str = "dev-only-not-a-secret"
    token_ttl_hours: int = 12


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
