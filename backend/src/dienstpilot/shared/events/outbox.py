"""Publishing: one INSERT into the outbox, in the caller's transaction."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from dienstpilot.shared.events import schemas
from dienstpilot.shared.events.models import Outbox


def publish(
    session: Session,
    event_type: str,
    payload: dict[str, Any],
    *,
    occurred_at: datetime,
    department_id: str | None,
    version: int | None = None,
) -> str:
    """Validate the payload against its schema and add the event to the outbox.

    The event commits or rolls back together with the state change. Payloads carry ids only:
    no names, no absence category.
    """
    v = version or schemas.latest(event_type)
    schemas.validate(event_type, v, payload)
    event_id = uuid.uuid4()
    session.add(
        Outbox(
            event_id=event_id,
            event_type=event_type,
            version=v,
            department_id=None if department_id is None else uuid.UUID(department_id),
            occurred_at=occurred_at,
            payload=payload,
        )
    )
    session.flush()
    return str(event_id)
