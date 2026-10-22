"""Workflow instances and demo-time timers (ADR-017).

Postgres is the only source of truth. A timer is a row with a ``due_at`` in *demo* time;
``fire_due`` runs every timer that has become due, one at a time, in (due_at, id) order, each
exactly once: a transaction-level advisory lock serialises the firing loop (an API read and the
worker can try at the same moment; one waits, then finds the timers done), and each timer row is
locked and marked fired in the same transaction as its handler's changes. A worker that dies in
the middle loses nothing: the transaction rolls back and the timer is still due.

The Redis queue only wakes the worker up; it never holds state.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from dienstpilot.shared.ports import Clock
from dienstpilot.shared.workflows.machines import MACHINES
from dienstpilot.shared.workflows.models import Instance, Timer

log = logging.getLogger(__name__)
LOCK_KEY = 7_340_001  # pg_advisory_xact_lock key of the firing loop
MAX_ATTEMPTS = 3
MAX_FIRED_PER_CALL = 5000


class IllegalTransitionError(ValueError):
    """The state machine does not allow this move."""


@dataclass(frozen=True)
class Env:
    """What a timer handler may use besides the session."""

    clock: Clock
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TimerView:
    """A due timer as the handler sees it. Effects are stamped ``due_at``, not "now"."""

    id: int
    kind: str
    key: str
    due_at: datetime
    payload: dict[str, Any]
    department_id: str | None


Handler = Callable[[Session, TimerView, Env], None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    """Register the function that runs when a timer of ``kind`` fires."""

    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


# --- instances --------------------------------------------------------------------------------


def start(
    session: Session, kind: str, key: str, now: datetime, data: dict[str, Any] | None = None
) -> None:
    """Create the instance in its initial state (no-op if it exists)."""
    session.execute(
        pg_insert(Instance)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            key=key,
            state=MACHINES[kind].initial,
            data=data or {},
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["kind", "key"])
    )


def ensure(
    session: Session,
    kind: str,
    key: str,
    state: str,
    now: datetime,
    data: dict[str, Any] | None = None,
) -> None:
    """Create the instance directly in ``state`` if it does not exist (rows older than this)."""
    session.execute(
        pg_insert(Instance)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            key=key,
            state=state,
            data=data or {},
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["kind", "key"])
    )


def get(session: Session, kind: str, key: str) -> Instance | None:
    """Return the instance, if any."""
    return session.scalars(
        select(Instance).where(Instance.kind == kind, Instance.key == key)
    ).first()


def move(
    session: Session,
    kind: str,
    key: str,
    to: str,
    now: datetime,
    data: dict[str, Any] | None = None,
) -> None:
    """Move an instance to ``to`` if the machine allows it (the row is locked meanwhile)."""
    inst = session.scalars(
        select(Instance).where(Instance.kind == kind, Instance.key == key).with_for_update()
    ).first()
    if inst is None:
        raise KeyError(f"{kind}/{key}")
    if not MACHINES[kind].allows(inst.state, to):
        raise IllegalTransitionError(f"{kind}: {inst.state} -> {to}")
    inst.state, inst.updated_at = to, now
    if data:
        inst.data = {**inst.data, **data}
    session.flush()


def state_of(session: Session, kind: str, key: str) -> str | None:
    """Return the instance's state."""
    inst = get(session, kind, key)
    return None if inst is None else inst.state


# --- timers -----------------------------------------------------------------------------------


def arm(
    session: Session,
    kind: str,
    key: str,
    due_at: datetime,
    *,
    department_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Set a timer due at ``due_at`` (demo time). Arming the same (kind, key) twice is a no-op."""
    res = session.execute(
        pg_insert(Timer)
        .values(
            kind=kind,
            key=key,
            due_at=due_at,
            department_id=None if department_id is None else uuid.UUID(department_id),
            payload=payload or {},
        )
        .on_conflict_do_nothing(index_elements=["kind", "key"])
        .returning(Timer.id)
    )
    return res.first() is not None


def rearm_future(session: Session, kind: str, key: str, now: datetime) -> None:
    """Make a fired timer pending again if the clock was moved back to before its due time.

    Only for recurring schedules (the nightly check), whose next occurrence must exist whatever
    happened to the clock; one-off timers are never un-fired (ADR-017).
    """
    for t in session.scalars(
        select(Timer)
        .where(
            Timer.kind == kind,
            Timer.key == key,
            Timer.fired_at.is_not(None),
            Timer.due_at > now,
        )
        .with_for_update()
    ):
        t.fired_at, t.attempts, t.last_error = None, 0, None
    session.flush()


def cancel(session: Session, kind: str, key: str, now: datetime) -> None:
    """Cancel a timer that has not fired."""
    for t in session.scalars(
        select(Timer)
        .where(
            Timer.kind == kind,
            Timer.key == key,
            Timer.fired_at.is_(None),
            Timer.cancelled_at.is_(None),
        )
        .with_for_update()
    ):
        t.cancelled_at = now
    session.flush()


def cancel_prefix(session: Session, kind: str, key_prefix: str, now: datetime) -> None:
    """Cancel every unfired timer of ``kind`` whose key starts with ``key_prefix``."""
    for t in session.scalars(
        select(Timer)
        .where(
            Timer.kind == kind,
            Timer.key.startswith(key_prefix),
            Timer.fired_at.is_(None),
            Timer.cancelled_at.is_(None),
        )
        .with_for_update()
    ):
        t.cancelled_at = now
    session.flush()


def _pending() -> Any:
    return (Timer.fired_at.is_(None), Timer.cancelled_at.is_(None), Timer.failed_at.is_(None))


def due_count(session: Session, now: datetime) -> int:
    """Return how many timers are due at ``now`` (no locks)."""
    return int(
        session.scalar(
            select(func.count()).select_from(Timer).where(Timer.due_at <= now, *_pending())
        )
        or 0
    )


def fire_due(session: Session, env: Env, now: datetime | None = None) -> list[tuple[str, str]]:
    """Fire every timer due at ``now`` (default: the demo clock), in order. Returns (kind, key).

    Safe to call from anywhere, any number of times, concurrently: each timer runs once. Call it
    at the start of a transaction (it may wait for another caller that is firing).
    """
    now = now or env.clock.now()
    if due_count(session, now) == 0:
        return []
    session.execute(select(func.pg_advisory_xact_lock(LOCK_KEY)))
    fired: list[tuple[str, str]] = []
    tried: set[int] = set()
    while len(fired) < MAX_FIRED_PER_CALL:
        t = session.scalars(
            select(Timer)
            .where(Timer.due_at <= now, Timer.id.not_in(tried), *_pending())
            .order_by(Timer.due_at, Timer.id)
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if t is None:
            break
        tried.add(t.id)
        view = TimerView(
            t.id,
            t.kind,
            t.key,
            t.due_at,
            dict(t.payload),
            None if t.department_id is None else str(t.department_id),
        )
        try:
            with session.begin_nested():
                HANDLERS[t.kind](session, view, env)
        except Exception as e:  # the handler's changes are rolled back; try again later
            log.exception("timer %s/%s failed", t.kind, t.key)
            t.attempts += 1
            t.last_error = repr(e)[:300]
            if t.attempts >= MAX_ATTEMPTS:
                t.failed_at = now
            session.flush()
            continue
        t.fired_at = now
        session.flush()
        fired.append((t.kind, t.key))
    return fired
