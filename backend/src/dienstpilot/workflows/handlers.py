"""Timer handlers and event consumers. Importing this module registers them."""

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from dienstpilot.audit import service as audit
from dienstpilot.notifications import service as notifications
from dienstpilot.operations import service as operations
from dienstpilot.organization import service as organization
from dienstpilot.recording import record
from dienstpilot.requests import service as requests
from dienstpilot.shared.events import outbox
from dienstpilot.shared.events.consumer import Consumer, Event
from dienstpilot.shared.settings import TZ
from dienstpilot.shared.workflows import engine, machines
from dienstpilot.shared.workflows.engine import Env, TimerView, handler
from dienstpilot.workflows import reminders

AUDIT_NIGHTLY = "audit.nightly"
MONTH_PREPARE = "month.prepare"
NIGHTLY_AT = time(2, 0)


# --- sick-call cascade: the 15-minute answer deadline -------------------------------------------


@handler(operations.COVER_TIMEOUT)
def cover_timeout(session: Session, t: TimerView, env: Env) -> None:
    """Nobody answered in time: ask the next colleague, or hand the cascade to the Planner."""
    res = operations.timeout_offer(session, t.key, t.payload["cascade_id"])
    if res is not None and not res[1]:
        outbox.publish(
            session,
            "CoverEscalated",
            {"cascade_id": t.payload["cascade_id"], "reason": operations.LIST_EXHAUSTED},
            occurred_at=t.due_at,
            department_id=t.department_id,
        )


# --- request-window reminders ------------------------------------------------------------------


@handler(reminders.KIND)
def window_reminder(session: Session, t: TimerView, env: Env) -> None:
    """Remind everyone who has not answered the window yet (in-app)."""
    window_id, _, tag = t.key.partition(":")
    window = next((w for w in requests.windows(session) if w.id == window_id), None)
    if window is None or window.status != "open" or t.department_id is None:
        return
    answered = requests.responses(session, window.id)
    staff = organization.staff(session, t.department_id)
    open_ones = [p for p in reminders.window_recipients(window, staff) if p.id not in answered]
    for p in open_ones:
        notifications.add(
            session,
            staff_id=p.id,
            kind="window_reminder",
            at=t.due_at,
            data={
                "roster_month": window.roster_month.isoformat(),
                "closes_at": window.closes_at.isoformat(),
            },
            key=f"window-reminder/{t.key}",
        )
    state = next(s for k, _, s in reminders.OFFSETS if k == tag)
    engine.ensure(session, machines.REQUEST_WINDOW, window.id, "open", t.due_at)
    inst = engine.state_of(session, machines.REQUEST_WINDOW, window.id)
    if inst is not None and machines.MACHINES[machines.REQUEST_WINDOW].allows(inst, state):
        engine.move(session, machines.REQUEST_WINDOW, window.id, state, t.due_at)
    record(
        session,
        occurred_at=t.due_at,
        department_id=t.department_id,
        actor_user_id=None,
        actor_label="System",
        action="window.reminder_sent",
        subject_type="request_window",
        subject_id=window.id,
        payload={"reminded": len(open_ones), "automatic": True, "days_before_close": tag},
    )


# --- nightly verification of the audit chain ----------------------------------------------------


def nightly_due(day: date) -> datetime:
    """Return 02:00 Berlin time of a day."""
    return datetime.combine(day, NIGHTLY_AT, tzinfo=TZ)


def arm_nightly(session: Session, department_id: str, after: datetime) -> None:
    """Set the next 02:00 check strictly after ``after``."""
    day = after.astimezone(TZ).date()
    due = nightly_due(day)
    if due <= after:
        due = nightly_due(day + timedelta(days=1))
    key = f"{department_id}:{due.date().isoformat()}"
    engine.arm(session, AUDIT_NIGHTLY, key, due, department_id=department_id)
    engine.rearm_future(session, AUDIT_NIGHTLY, key, after)


def ensure_nightly(session: Session, now: datetime) -> None:
    """Make sure every department has its next 02:00 check, wherever the clock has been."""
    for department_id in audit.departments(session):
        arm_nightly(session, department_id, now)


@handler(AUDIT_NIGHTLY)
def audit_nightly(session: Session, t: TimerView, env: Env) -> None:
    """Verify the whole chain, then set the next night. A jump over several days checks once."""
    assert t.department_id is not None
    audit.run_check(session, t.department_id, t.due_at, "nightly")
    now = env.clock.now()
    # Nights the clock jumped over are collapsed into one check: re-arm at the last 02:00 <= now.
    day = t.due_at.astimezone(TZ).date() + timedelta(days=1)
    while nightly_due(day + timedelta(days=1)) <= now:
        day += timedelta(days=1)
    engine.arm(
        session,
        AUDIT_NIGHTLY,
        f"{t.department_id}:{day.isoformat()}",
        nightly_due(day),
        department_id=t.department_id,
    )


# --- month end ----------------------------------------------------------------------------------


def month_due(month: date) -> datetime:
    """Return the instant a month is over: 00:00 Berlin time on the first day after it."""
    nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return datetime.combine(nxt, time(0, 0), tzinfo=TZ)


def arm_month_end(session: Session, department_id: str, month: date, now: datetime) -> None:
    """Prepare the documentation of ``month`` as soon as it is over (in demo time)."""
    engine.start(session, machines.MONTH_END, f"{department_id}:{month:%Y-%m}", now)
    engine.arm(
        session,
        MONTH_PREPARE,
        f"{department_id}:{month:%Y-%m}",
        month_due(month),
        department_id=department_id,
    )


@handler(MONTH_PREPARE)
def month_prepare(session: Session, t: TimerView, env: Env) -> None:
    """Compute and store the month-end report (hours, overtime, rest, burden, decision trail)."""
    from dienstpilot.app.month_report import prepare

    assert t.department_id is not None
    month = date.fromisoformat(t.key.split(":")[1] + "-01")
    prepare(session, env.extras["engines"], t.department_id, month, t.due_at)


def month_closed(session: Session, event: Event) -> None:
    """Consumer of MonthClosed: set up the preparation of the following month."""
    if event.department_id is None:
        return
    closed = date.fromisoformat(event.payload["roster_month"])
    following = date(closed.year + (closed.month == 12), closed.month % 12 + 1, 1)
    arm_month_end(session, event.department_id, following, event.occurred_at)


CONSUMERS = [Consumer("month_end", {"MonthClosed": month_closed})]
