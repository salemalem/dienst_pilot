"""Tables of the event pipeline (schema ``events``)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import EventsBase as Base


class Outbox(Base):
    """An event, written in the same transaction as the state change that caused it."""

    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_unrelayed", "seq", postgresql_where="relayed_at IS NULL"),)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(40))
    version: Mapped[int]
    department_id: Mapped[uuid.UUID | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    relayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stream_id: Mapped[str | None] = mapped_column(String(40))


class Processed(Base):
    """That a consumer has handled an event: the idempotency key is (consumer, event_id)."""

    __tablename__ = "processed"
    consumer: Mapped[str] = mapped_column(String(40), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
