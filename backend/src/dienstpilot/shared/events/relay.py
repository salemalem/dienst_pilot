"""The relay: outbox rows to the stream, oldest first, at least once."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from dienstpilot.shared.events.models import Outbox
from dienstpilot.shared.events.stream import EventStream, encode


def relay(session: Session, stream: EventStream, now: datetime, batch: int = 200) -> int:
    """Send unrelayed events to the stream and mark them. Returns how many were sent.

    Rows are locked with SKIP LOCKED, so two relays never send the same row at once. If the
    process dies between XADD and the commit the row is sent again: consumers deduplicate on
    ``event_id``.
    """
    sent = 0
    while True:
        rows = list(
            session.scalars(
                select(Outbox)
                .where(Outbox.relayed_at.is_(None))
                .order_by(Outbox.seq)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.stream_id = stream.add(
                encode(
                    str(row.event_id),
                    row.event_type,
                    row.version,
                    None if row.department_id is None else str(row.department_id),
                    row.occurred_at.isoformat(),
                    row.payload,
                )
            )
            row.relayed_at = now
            sent += 1
        session.flush()
        if len(rows) < batch:
            return sent
