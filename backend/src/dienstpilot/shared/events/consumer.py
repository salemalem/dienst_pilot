"""Idempotent consumers: one consumer group each, event ids deduplicated per consumer."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from dienstpilot.shared.events.models import Processed
from dienstpilot.shared.events.stream import EventStream


@dataclass(frozen=True)
class Event:
    """A delivered event."""

    event_id: str
    event_type: str
    version: int
    department_id: str | None
    occurred_at: datetime
    payload: dict[str, Any]


EventHandler = Callable[[Session, Event], None]


@dataclass(frozen=True)
class Consumer:
    """A named consumer and the event types it handles (handlers receive every version)."""

    name: str
    handlers: dict[str, EventHandler]


def decode(fields: dict[str, str]) -> Event:
    """Rebuild an event from a stream entry."""
    return Event(
        fields["event_id"],
        fields["event_type"],
        int(fields["version"]),
        fields["department_id"] or None,
        datetime.fromisoformat(fields["occurred_at"]),
        json.loads(fields["payload"]),
    )


def consume(
    session: Session, stream: EventStream, consumer: Consumer, now: datetime, count: int = 100
) -> int:
    """Handle the next entries for ``consumer``. Returns how many handler calls ran.

    Per entry, in one transaction: insert (consumer, event_id) into ``processed``; if that row is
    new, run the handler; commit; then acknowledge. A crash after the commit but before the
    acknowledgement redelivers the entry, the insert finds the row, and the handler is skipped. A
    handler that raises rolls everything back and leaves the entry pending for the next call.
    """
    ran = 0
    for msg in stream.read(consumer.name, consumer.name, count):
        event = decode(msg.fields)
        try:
            with session.begin_nested():
                new = session.execute(
                    pg_insert(Processed)
                    .values(
                        consumer=consumer.name,
                        event_id=uuid.UUID(event.event_id),
                        processed_at=now,
                    )
                    .on_conflict_do_nothing()
                    .returning(Processed.event_id)
                ).first()
                handle = consumer.handlers.get(event.event_type)
                if new is not None and handle is not None:
                    handle(session, event)
                    ran += 1
        except Exception:
            return ran  # leave it pending; the next call retries
        session.commit()
        stream.ack(consumer.name, msg.id)
    return ran
