"""Error responses shared by all routes."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dienstpilot.shared.ports import EngineNotImplementedError


def not_implemented_body(err: EngineNotImplementedError) -> dict[str, object]:
    """Return the 501 body: which component is missing and when it arrives."""
    return {
        "detail": {
            "code": "engine_not_implemented",
            "component": err.info.component,
            "planned_phase": err.info.planned_phase,
            "message": f"{err.info.component} is not implemented yet: {err.info.note}",
        }
    }


def install(app: FastAPI) -> None:
    """Register the exception handlers."""

    @app.exception_handler(EngineNotImplementedError)
    async def _not_implemented(request: Request, err: EngineNotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content=not_implemented_body(err))
