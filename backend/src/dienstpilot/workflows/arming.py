"""Timers every department needs from the start (set when the database is seeded)."""

from datetime import datetime

from sqlalchemy.orm import Session

from dienstpilot.requests import service as requests
from dienstpilot.workflows import handlers, reminders


def arm_defaults(session: Session, department_id: str, now: datetime) -> None:
    """Arm the nightly chain check, the reminders of open windows and this month's report."""
    handlers.arm_nightly(session, department_id, now)
    for window in requests.windows(session):
        reminders.arm(session, window, department_id, now)
    handlers.arm_month_end(session, department_id, now.date().replace(day=1), now)
