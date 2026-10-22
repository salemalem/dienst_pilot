"""Fire due timers from the places that need the world to be up to date."""

from sqlalchemy.orm import Session

from dienstpilot.shared.ports import Clock
from dienstpilot.shared.workflows import engine


def settle(session: Session, clock: Clock, engines: object | None) -> list[tuple[str, str]]:
    """Fire every timer that is due at the demo clock's time, in order, exactly once.

    Call it first thing in a request or job, before the code reads or writes anything the timers
    may change (it can wait for another caller that is firing, and that is the point: when it
    returns, everything due has been done). Returns what fired as (kind, key).
    """
    from dienstpilot.workflows import handlers

    handlers.ensure_nightly(session, clock.now())
    return engine.fire_due(session, engine.Env(clock, {"engines": engines}))
