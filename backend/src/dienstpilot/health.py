"""Liveness and readiness checks for the API process and its backing services."""

from typing import Literal

import redis.asyncio as aioredis
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from dienstpilot.shared.settings import Settings

CheckStatus = Literal["ok", "fail"]


class Health(BaseModel):
    """Liveness response."""

    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    """Readiness response: one entry per backing service."""

    status: CheckStatus
    postgres: CheckStatus
    pgvector: CheckStatus
    redis: CheckStatus


async def check_postgres(settings: Settings) -> tuple[CheckStatus, CheckStatus]:
    """Return (postgres reachable, pgvector extension installed)."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            row = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return "ok", "ok" if row.first() is not None else "fail"
    except Exception:
        return "fail", "fail"
    finally:
        await engine.dispose()


async def check_redis(settings: Settings) -> CheckStatus:
    """Return whether Redis answers a PING."""
    client = aioredis.from_url(settings.redis_url)
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "fail"
    finally:
        await client.aclose()
