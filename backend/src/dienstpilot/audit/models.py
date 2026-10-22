"""Append-only audit events."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Identity, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import AuditBase as Base


class Event(Base):
    """One audit event. Never updated or deleted."""

    __tablename__ = "event"
    __table_args__ = (
        Index("ix_event_occurred_at", "occurred_at"),
        Index("uq_event_chain_seq", "chain_key", "seq", unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # None: an event that belongs to no department (the "system" chain, e.g. a clock change).
    department_id: Mapped[uuid.UUID | None]
    # The hash chain (ADR-016): "system" or the department id; seq counts from 1 without gaps.
    chain_key: Mapped[str] = mapped_column(String(40))
    seq: Mapped[int] = mapped_column(BigInteger)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    actor_user_id: Mapped[uuid.UUID | None]
    actor_label: Mapped[str] = mapped_column(String(200))  # display name, "System" or "Import"
    action: Mapped[str] = mapped_column(String(60), index=True)
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID | None]
    staff_id: Mapped[uuid.UUID | None] = mapped_column(index=True)  # whom it concerns, if anyone
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ChainHead(Base):
    """The newest event of a chain. Locked while appending, so seq and prev_hash never fork."""

    __tablename__ = "chain_head"
    chain_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    head_seq: Mapped[int] = mapped_column(BigInteger)
    head_hash: Mapped[str] = mapped_column(String(64))


class ChainCheck(Base):
    """The outcome of one run of the verifier."""

    __tablename__ = "chain_check"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # also the order
    chain_key: Mapped[str] = mapped_column(String(40), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # demo time
    trigger: Mapped[str] = mapped_column(String(10))  # nightly | on_demand | seed
    ok: Mapped[bool] = mapped_column(Boolean)
    rows: Mapped[int] = mapped_column(BigInteger)
    head_seq: Mapped[int] = mapped_column(BigInteger)
    head_hash: Mapped[str] = mapped_column(String(64))
    first_bad_seq: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(String(200))
