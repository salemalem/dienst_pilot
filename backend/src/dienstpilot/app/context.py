"""Builds the per-request Ctx for route handlers."""

from typing import Annotated

from fastapi import Depends

from dienstpilot.app.deps import ClockDep, Ctx, EnginesDep, SessionDep, UserDep


def ctx(session: SessionDep, clock: ClockDep, engines: EnginesDep, user: UserDep) -> Ctx:
    """Return the request context of an authenticated request."""
    return Ctx(session, clock, engines, user)


CtxDep = Annotated[Ctx, Depends(ctx)]
