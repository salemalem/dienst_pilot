"""Request-scoped dependencies: session, clock, engines and the authenticated user."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import redis
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from dienstpilot.engines.registry import Engines, default_engines
from dienstpilot.identity import service as identity
from dienstpilot.identity.service import UserView
from dienstpilot.identity.tokens import InvalidTokenError, verify
from dienstpilot.shared.clock import RedisClock
from dienstpilot.shared.database import get_session
from dienstpilot.shared.ports import Clock
from dienstpilot.shared.settings import Settings, get_settings

STAFF_ROLES = ("staff", "staff_plus", "planner")


@lru_cache
def _redis(url: str) -> redis.Redis:
    return redis.Redis.from_url(url)


def get_clock(settings: Annotated[Settings, Depends(get_settings)]) -> Clock:
    """Return the demo clock (overridden in tests)."""
    return RedisClock(_redis(settings.redis_url), settings.demo_now)


@lru_cache
def get_engines() -> Engines:
    """Return the engine implementations (overridden in tests if needed)."""
    return default_engines()


# scope="function": the session commits after the handler and BEFORE the response is sent. With the
# default scope the commit ran after the response, so a client's next request could read the old
# state (a read-after-write race that showed up as flaky e2e tests).
SessionDep = Annotated[Session, Depends(get_session, scope="function")]
ClockDep = Annotated[Clock, Depends(get_clock)]
EnginesDep = Annotated[Engines, Depends(get_engines)]


def current_user(
    session: SessionDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> UserView:
    """Return the user of a valid bearer token, else 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first (POST /auth/demo-login).")
    try:
        claims = verify(authorization.split(" ", 1)[1], settings.token_secret, clock.now())
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}") from e
    user = identity.by_id(session, claims.user_id)
    if user is None or user.role != claims.role or user.department_id != claims.department_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


UserDep = Annotated[UserView, Depends(current_user)]


def require(*roles: str) -> Callable[[UserView], UserView]:
    """Return a dependency that allows only the given roles (403 otherwise)."""

    def check(user: UserDep) -> UserView:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not allowed for role {user.role}")
        return user

    return check


def physician(user: UserDep) -> UserView:
    """Allow only users who are physicians of the department (they have a staff record)."""
    if user.staff_id is None or user.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only for physicians of the department")
    return user


PhysicianDep = Annotated[UserView, Depends(physician)]
PlannerDep = Annotated[UserView, Depends(require("planner"))]
RosterReaderDep = Annotated[UserView, Depends(require("staff_plus", "planner"))]
OversightReaderDep = Annotated[UserView, Depends(require("planner", "oversight"))]
AdminDep = Annotated[UserView, Depends(require("admin"))]
MasterDataReaderDep = Annotated[UserView, Depends(require("admin", "planner"))]


@dataclass(frozen=True)
class Ctx:
    """Everything a handler needs, in one object."""

    session: Session
    clock: Clock
    engines: Engines
    user: UserView
