"""FastAPI application entry point."""

from typing import Annotated

from fastapi import Depends, FastAPI, Response, status

from dienstpilot import health
from dienstpilot.shared.settings import Settings, get_settings

app = FastAPI(title="DienstPilot API", version="0.1.0")


@app.get("/health", tags=["health"])
async def get_health() -> health.Health:
    """Liveness: the API process is running."""
    return health.Health()


@app.get("/health/ready", tags=["health"])
async def get_readiness(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> health.Readiness:
    """Readiness: Postgres (with pgvector) and Redis are reachable. 503 if any check fails."""
    postgres, pgvector = await health.check_postgres(settings)
    redis = await health.check_redis(settings)
    ok = postgres == pgvector == redis == "ok"
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health.Readiness(
        status="ok" if ok else "fail", postgres=postgres, pgvector=pgvector, redis=redis
    )
