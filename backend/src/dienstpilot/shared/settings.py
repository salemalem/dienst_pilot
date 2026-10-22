"""Runtime configuration, read from the environment (and an optional .env file)."""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

TZ = ZoneInfo("Europe/Berlin")
# UI_SPEC §1: the demo moment, Tuesday 20 October 2026, 06:00 Europe/Berlin.
DEMO_NOW = datetime(2026, 10, 20, 6, 0, tzinfo=TZ)


class Settings(BaseSettings):
    """Application settings. Every value can be overridden by an environment variable."""

    # The repository's .env (git-ignored) and one in the working directory; the environment wins.
    model_config = SettingsConfigDict(
        env_file=(str(Path(__file__).resolve().parents[4] / ".env"), ".env"), extra="ignore"
    )

    database_url: str = "postgresql+psycopg://dienstpilot:dienstpilot@localhost:5433/dienstpilot"
    redis_url: str = "redis://localhost:6379/0"
    llm_model_intake: str = "claude-haiku-5-5"
    llm_model_copilot: str = "claude-sonnet-5-5"
    # The Anthropic key comes only from the environment or the git-ignored .env, never from code.
    # Without it C7 and C8 run as their labelled stand-ins (Phase 10).
    anthropic_api_key: SecretStr | None = None
    # The instant the demo clock shows unless an Administrator moves it (DEMO_MODE only).
    demo_now: datetime = DEMO_NOW
    # Registers the demo endpoints (PUT /demo/clock). On in the dev stack, off otherwise.
    demo_mode: bool = False
    # Browser origins that may call the API, comma separated. Used only when DEMO_MODE is on
    # (Expo web in development and in the e2e run); without DEMO_MODE the API sends no CORS headers.
    cors_origins: str = "http://localhost:8081,http://localhost:8083"
    # Rule search (RAG): which retrieval is served. "vector" is the evaluated champion; "hybrid"
    # (full-text + vectors) stays available for the follow-up (ADR-019). Without the bge-m3 model
    # files every setting falls back to full-text only, and the response says so.
    rag_retrieval: Literal["vector", "hybrid", "fts"] = "vector"
    bge_m3_dir: str | None = None
    # Signs demo-login tokens. The default is for local development only.
    token_secret: str = "dev-only-not-a-secret"
    token_ttl_hours: int = 12


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
