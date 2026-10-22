"""FastAPI application entry point."""

from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from dienstpilot import health
from dienstpilot.app.routes import auth, insight, me, months, planner, rules
from dienstpilot.shared.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. The demo endpoints exist only when DEMO_MODE is on."""
    settings = settings or get_settings()
    app = FastAPI(
        title="DienstPilot API",
        version="0.2.0",
        description=(
            "Demo environment, synthetic data."
            " Fictional Klinik für Innere Medizin, Klinikum Musterstadt."
        ),
    )

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

    for router in (
        auth.router,
        me.router,
        planner.router,
        insight.router,
        months.router,
        rules.router,
    ):
        app.include_router(router)
    if settings.demo_mode:
        app.include_router(auth.demo_router)
        # Dev origins only, bearer tokens (no cookies), explicit methods and headers (ADR-011).
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
            allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
            allow_headers=["authorization", "content-type"],
            allow_credentials=False,
        )
    return app


app = create_app()
