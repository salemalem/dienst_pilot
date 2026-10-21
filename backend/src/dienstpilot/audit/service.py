"""Public interface of the audit context: record and read events. No update, no delete."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from dienstpilot.audit.models import Event


@dataclass(frozen=True)
class EventView:
    """An audit event as stored (the API layer applies privacy rules before showing it)."""

    id: str
    occurred_at: datetime
    actor_label: str
    action: str
    subject_type: str
    subject_id: str | None
    staff_id: str | None
    payload: dict[str, Any]


def record(
    session: Session,
    *,
    occurred_at: datetime,
    department_id: str,
    actor_user_id: str | None,
    actor_label: str,
    action: str,
    subject_type: str,
    subject_id: str | None = None,
    staff_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Append one event and return its id."""
    key = f"{action}/{occurred_at.isoformat()}" + (f"/{staff_id}" if staff_id else "")
    event_id = uuid.uuid4() if subject_id is None else uuid.uuid5(uuid.UUID(subject_id), key)
    session.add(
        Event(
            id=event_id,
            occurred_at=occurred_at,
            department_id=uuid.UUID(department_id),
            actor_user_id=None if actor_user_id is None else uuid.UUID(actor_user_id),
            actor_label=actor_label,
            action=action,
            subject_type=subject_type,
            subject_id=None if subject_id is None else uuid.UUID(subject_id),
            staff_id=None if staff_id is None else uuid.UUID(staff_id),
            payload=payload or {},
        )
    )
    session.flush()
    return str(event_id)


def _query(
    department_id: str,
    action_prefix: str | None,
    staff_id: str | None,
    since: datetime | None,
    until: datetime | None,
) -> Select[Event]:
    q = select(Event).where(Event.department_id == uuid.UUID(department_id))
    if action_prefix:
        q = q.where(Event.action.startswith(action_prefix))
    if staff_id:
        q = q.where(Event.staff_id == uuid.UUID(staff_id))
    if since:
        q = q.where(Event.occurred_at >= since)
    if until:
        q = q.where(Event.occurred_at <= until)
    return q


def list_events(
    session: Session,
    department_id: str,
    *,
    action_prefix: str | None = None,
    staff_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[EventView]]:
    """Return (total, page) of events, newest first."""
    q = _query(department_id, action_prefix, staff_id, since, until)
    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = session.scalars(
        q.order_by(Event.occurred_at.desc(), Event.id).limit(limit).offset(offset)
    )
    return total, [
        EventView(
            str(e.id),
            e.occurred_at,
            e.actor_label,
            e.action,
            e.subject_type,
            None if e.subject_id is None else str(e.subject_id),
            None if e.staff_id is None else str(e.staff_id),
            dict(e.payload),
        )
        for e in rows
    ]
