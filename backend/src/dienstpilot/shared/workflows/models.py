"""Tables of the workflow engine (schema ``workflow``)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import WorkflowBase as Base


class Instance(Base):
    """One running or finished workflow: its kind, a business key and its state."""

    __tablename__ = "instance"
    __table_args__ = (Index("uq_instance_kind_key", "kind", "key", unique=True),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    key: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Timer(Base):
    """A timer due at an instant of demo time. Fired exactly once, in (due_at, id) order."""

    __tablename__ = "timer"
    __table_args__ = (
        Index("uq_timer_kind_key", "kind", "key", unique=True),
        Index(
            "ix_timer_due",
            "due_at",
            "id",
            postgresql_where=text(
                "fired_at IS NULL AND cancelled_at IS NULL AND failed_at IS NULL"
            ),
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(120))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    department_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
