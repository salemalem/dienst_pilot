"""M1: demo sign-in with a persona; the current user; the demo clock."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from dienstpilot.app.context import CtxDep
from dienstpilot.app.deps import AdminDep, ClockDep, SessionDep, get_clock
from dienstpilot.audit import service as audit
from dienstpilot.identity import service as identity
from dienstpilot.identity.tokens import Claims, expiry, issue
from dienstpilot.shared.clock import RedisClock
from dienstpilot.shared.ports import Clock
from dienstpilot.shared.settings import Settings, get_settings

router = APIRouter(tags=["auth"])


class Persona(BaseModel):
    """A demo persona."""

    key: str
    display_name: str
    role: str


class LoginRequest(BaseModel):
    """Which persona to sign in as."""

    persona: str


class Token(BaseModel):
    """A bearer token for the persona."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: "Me"


class Me(BaseModel):
    """The signed-in user."""

    id: str
    persona_key: str
    display_name: str
    role: str
    department_id: str
    staff_id: str | None


class ClockOut(BaseModel):
    """The demo clock."""

    now: datetime
    demo_mode: bool


@router.get("/auth/personas")
def personas(session: SessionDep) -> list[Persona]:
    """List the demo personas (UI_SPEC §1)."""
    return [
        Persona(key=u.persona_key, display_name=u.display_name, role=u.role)
        for u in identity.personas(session)
    ]


@router.post("/auth/demo-login")
def demo_login(
    body: LoginRequest,
    session: SessionDep,
    clock: ClockDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Token:
    """Sign in as a demo persona. Real single sign-on replaces this later."""
    user = identity.by_persona(session, body.persona)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown persona")
    exp = expiry(clock.now(), settings.token_ttl_hours)
    token = issue(Claims(user.id, user.role, user.department_id, exp), settings.token_secret)
    return Token(access_token=token, expires_at=exp, user=Me(**user.__dict__))


@router.get("/me")
def me(c: CtxDep) -> Me:
    """Return the signed-in user."""
    return Me(**c.user.__dict__)


@router.get("/clock")
def clock_now(clock: ClockDep, settings: Annotated[Settings, Depends(get_settings)]) -> ClockOut:
    """Return the demo clock (the UI uses it for "today" and countdowns)."""
    return ClockOut(now=clock.now(), demo_mode=settings.demo_mode)


class ClockIn(BaseModel):
    """A new demo time, or reset to the default demo moment."""

    now: datetime | None = None
    reset: bool = False


demo_router = APIRouter(tags=["demo"])


@demo_router.put("/demo/clock")
def set_clock(
    body: ClockIn,
    admin: AdminDep,
    session: SessionDep,
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClockOut:
    """Move the demo clock (Administrator, DEMO_MODE only). Stored in Redis."""
    if not isinstance(clock, RedisClock):
        raise HTTPException(status.HTTP_409_CONFLICT, "This clock cannot be moved")
    if body.reset:
        clock.reset()
    elif body.now is None or body.now.tzinfo is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Give a timezone-aware time or reset"
        )
    else:
        clock.set(body.now)
    audit.record(
        session,
        occurred_at=clock.now(),
        department_id=admin.department_id,
        actor_user_id=admin.id,
        actor_label=admin.display_name,
        action="demo.clock_set",
        subject_type="clock",
        payload={"now": clock.now().isoformat()},
    )
    return ClockOut(now=clock.now(), demo_mode=settings.demo_mode)
