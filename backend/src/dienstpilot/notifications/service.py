"""Public interface of the notifications context."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dienstpilot.notifications import models as m


@dataclass(frozen=True)
class StoredNotification:
    """A stored notification."""

    kind: str
    at: datetime
    data: dict[str, Any]


def add(
    session: Session,
    *,
    staff_id: str,
    kind: str,
    at: datetime,
    data: dict[str, Any],
    key: str,
) -> bool:
    """Store a notification once: ``key`` makes a re-run (same reminder, same person) a no-op."""
    nid = uuid.uuid5(uuid.NAMESPACE_URL, f"dienstpilot/notification/{key}/{staff_id}")
    if session.get(m.Notification, nid) is not None:
        return False
    session.add(
        m.Notification(id=nid, staff_id=uuid.UUID(staff_id), kind=kind, created_at=at, data=data)
    )
    session.flush()
    return True


def for_staff(session: Session, staff_id: str, until: datetime) -> list[StoredNotification]:
    """Return a physician's stored notifications up to ``until``, newest first."""
    rows = session.scalars(
        select(m.Notification)
        .where(m.Notification.staff_id == uuid.UUID(staff_id), m.Notification.created_at <= until)
        .order_by(m.Notification.created_at.desc())
    )
    return [StoredNotification(n.kind, n.created_at, dict(n.data)) for n in rows]
