"""Append-only audit events."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import AuditBase as Base


class Event(Base):
    """One audit event. Never updated or deleted."""

    __tablename__ = "event"
    __table_args__ = (Index("ix_event_occurred_at", "occurred_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    department_id: Mapped[uuid.UUID]
    actor_user_id: Mapped[uuid.UUID | None]
    actor_label: Mapped[str] = mapped_column(String(200))  # display name, "System" or "Import"
    action: Mapped[str] = mapped_column(String(60), index=True)
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID | None]
    staff_id: Mapped[uuid.UUID | None] = mapped_column(index=True)  # whom it concerns, if anyone
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
