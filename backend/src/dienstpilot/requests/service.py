"""Public interface of the requests context: request windows, answers, preferences, leave."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from dienstpilot.requests import models as m


@dataclass(frozen=True)
class Window:
    """A request window (Wunschphase)."""

    id: str
    roster_month: date
    opens_at: datetime
    closes_at: datetime
    status: str
    recipient_count: int


@dataclass(frozen=True)
class PreferenceEntry:
    """One request-window entry."""

    staff_id: str
    day: date
    kind: str  # unavailable | wish_work
    shift_type: str | None
    important: bool


@dataclass(frozen=True)
class LeaveRequest:
    """A leave request. There is no field for the requester's reason."""

    id: str
    staff_id: str
    start_date: date
    end_date: date
    submitted_at: datetime
    status: str
    decided_at: datetime | None
    decided_by: str | None
    decision_reason_code: str | None
    decision_reason: str | None
    previous_request_id: str | None


def _window(w: m.RequestWindow) -> Window:
    return Window(str(w.id), w.roster_month, w.opens_at, w.closes_at, w.status, w.recipient_count)


def windows(session: Session) -> list[Window]:
    """Return all request windows, newest month first."""
    return [
        _window(w)
        for w in session.scalars(
            select(m.RequestWindow).order_by(m.RequestWindow.roster_month.desc())
        )
    ]


def window_for(session: Session, month: date) -> Window | None:
    """Return the window of a roster month."""
    w = session.scalar(select(m.RequestWindow).where(m.RequestWindow.roster_month == month))
    return None if w is None else _window(w)


def responses(session: Session, window_id: str) -> dict[str, datetime]:
    """Return who answered a window, and when."""
    q = select(m.WindowResponse).where(m.WindowResponse.window_id == uuid.UUID(window_id))
    return {str(r.staff_id): r.submitted_at for r in session.scalars(q)}


def preferences(
    session: Session, window_id: str, staff_id: str | None = None
) -> list[PreferenceEntry]:
    """Return a window's entries, optionally of one person."""
    q = select(m.Preference).where(m.Preference.window_id == uuid.UUID(window_id))
    if staff_id is not None:
        q = q.where(m.Preference.staff_id == uuid.UUID(staff_id))
    return [
        PreferenceEntry(str(p.staff_id), p.date, p.kind, p.shift_type, p.important)
        for p in session.scalars(q.order_by(m.Preference.date))
    ]


def wishes_of(session: Session, staff_id: str) -> list[PreferenceEntry]:
    """Return every entry a person ever made (for preference suggestions)."""
    q = select(m.Preference).where(m.Preference.staff_id == uuid.UUID(staff_id))
    return [
        PreferenceEntry(str(p.staff_id), p.date, p.kind, p.shift_type, p.important)
        for p in session.scalars(q)
    ]


def submit(
    session: Session, window_id: str, staff_id: str, entries: list[PreferenceEntry], now: datetime
) -> None:
    """Replace a person's answer to a window."""
    wid, sid = uuid.UUID(window_id), uuid.UUID(staff_id)
    session.execute(
        delete(m.Preference).where(m.Preference.window_id == wid, m.Preference.staff_id == sid)
    )
    for i, e in enumerate(entries):
        session.add(
            m.Preference(
                id=uuid.uuid5(wid, f"{staff_id}/{i}/{now.isoformat()}"),
                window_id=wid,
                staff_id=sid,
                date=e.day,
                kind=e.kind,
                shift_type=e.shift_type,
                important=e.important,
            )
        )
    session.merge(m.WindowResponse(window_id=wid, staff_id=sid, submitted_at=now))
    session.flush()


def set_window_status(session: Session, window_id: str, status: str) -> None:
    """Open or close a window."""
    w = session.get(m.RequestWindow, uuid.UUID(window_id))
    if w is None:
        raise KeyError(window_id)
    w.status = status
    session.flush()


def _leave(r: m.LeaveRequest) -> LeaveRequest:
    return LeaveRequest(
        str(r.id),
        str(r.staff_id),
        r.start_date,
        r.end_date,
        r.submitted_at,
        r.status,
        r.decided_at,
        None if r.decided_by is None else str(r.decided_by),
        r.decision_reason_code,
        r.decision_reason,
        None if r.previous_request_id is None else str(r.previous_request_id),
    )


def leave_requests(
    session: Session,
    staff_ids: list[str],
    *,
    status: str | None = None,
    overlapping: tuple[date, date] | None = None,
) -> list[LeaveRequest]:
    """Return leave requests of the given people, optionally filtered."""
    q = select(m.LeaveRequest).where(m.LeaveRequest.staff_id.in_([uuid.UUID(s) for s in staff_ids]))
    if status is not None:
        q = q.where(m.LeaveRequest.status == status)
    if overlapping is not None:
        q = q.where(
            m.LeaveRequest.end_date >= overlapping[0], m.LeaveRequest.start_date <= overlapping[1]
        )
    return [_leave(r) for r in session.scalars(q.order_by(m.LeaveRequest.submitted_at.desc()))]


def leave_request(session: Session, request_id: str) -> LeaveRequest | None:
    """Return one leave request."""
    r = session.get(m.LeaveRequest, uuid.UUID(request_id))
    return None if r is None else _leave(r)


def create_leave(
    session: Session, staff_id: str, start: date, end: date, now: datetime
) -> LeaveRequest:
    """File a leave request (pending until the Planner decides)."""
    r = m.LeaveRequest(
        id=uuid.uuid5(uuid.UUID(staff_id), f"leave/{start}/{end}/{now.isoformat()}"),
        staff_id=uuid.UUID(staff_id),
        start_date=start,
        end_date=end,
        submitted_at=now,
        status="pending",
    )
    session.add(r)
    session.flush()
    return _leave(r)


def decide_leave(
    session: Session,
    request_id: str,
    approve: bool,
    decided_by: str | None,
    reason: str | None,
    now: datetime,
) -> LeaveRequest:
    """Record the Planner's decision. A decline needs the Planner's reason."""
    r = session.get(m.LeaveRequest, uuid.UUID(request_id))
    if r is None:
        raise KeyError(request_id)
    if r.status != "pending":
        raise ValueError("already decided")
    r.status = "approved" if approve else "declined"
    r.decided_at = now
    r.decided_by = None if decided_by is None else uuid.UUID(decided_by)
    r.decision_reason_code = None if approve else "planner"
    r.decision_reason = None if approve else reason
    session.flush()
    return _leave(r)
