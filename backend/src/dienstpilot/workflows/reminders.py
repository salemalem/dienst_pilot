"""Request-window reminders: in-app, 7 and 2 days before the window closes, non-responders only."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from dienstpilot.organization.service import StaffMember
from dienstpilot.requests.service import Window
from dienstpilot.shared.workflows import engine, machines

KIND = "window.reminder"
OFFSETS = (("7d", timedelta(days=7), "reminded_7d"), ("2d", timedelta(days=2), "reminded_2d"))


def window_recipients(window: Window, staff: Iterable[StaffMember]) -> list[StaffMember]:
    """Return who receives a request window (rostered at some point in its month, with a role)."""
    opened = window.opens_at.date()
    return [
        p
        for p in staff
        if p.role_on(opened) is not None
        and any(p.rostered_on(window.roster_month + timedelta(days=i)) for i in range(28))
    ]


def arm(session: Session, window: Window, department_id: str, now: datetime) -> None:
    """Start the workflow of an open window and set the reminders that are still ahead."""
    if window.status != "open":
        return
    engine.start(session, machines.REQUEST_WINDOW, window.id, now)
    for tag, before, _ in OFFSETS:
        due = window.closes_at - before
        if due > now:
            engine.arm(session, KIND, f"{window.id}:{tag}", due, department_id=department_id)


def closed(session: Session, window_id: str, now: datetime) -> None:
    """Stop the reminders of a window that was closed."""
    engine.cancel_prefix(session, KIND, f"{window_id}:", now)
    engine.ensure(session, machines.REQUEST_WINDOW, window_id, "open", now)
    engine.move(session, machines.REQUEST_WINDOW, window_id, "closed", now)
