"""Requests: request windows, answers, preferences and leave requests.

Staff ids and shift-type codes refer to the organization context by value; there are no
foreign keys across contexts.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import RequestsBase as Base


class RequestWindow(Base):
    """A Wunschphase for one roster month."""

    __tablename__ = "request_window"
    __table_args__ = (CheckConstraint("status IN ('open','closed')", name="status"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    roster_month: Mapped[date] = mapped_column(Date, unique=True)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10))
    recipient_count: Mapped[int]


class WindowResponse(Base):
    """That a physician answered a window (an answer may contain no entries)."""

    __tablename__ = "window_response"
    window_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("request_window.id"), primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Preference(Base):
    """One entry of a request window.

    A day the physician cannot work, wants to work (optionally a shift), or would rather not work
    a given shift on (soft, never a block).
    """

    __tablename__ = "preference"
    __table_args__ = (
        CheckConstraint("kind IN ('unavailable','wish_work','avoid_shift')", name="kind"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    window_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("request_window.id"), index=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))
    shift_type: Mapped[str | None] = mapped_column(String(20))
    important: Mapped[bool]


class LeaveRequest(Base):
    """A leave request. Only the planner's reason for a decline is stored, never the requester's."""

    __tablename__ = "leave_request"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','declined')", name="status"),
        CheckConstraint(
            "decision_reason IS NULL OR status = 'declined'", name="reason_only_for_declines"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None]
    decision_reason_code: Mapped[str | None] = mapped_column(String(40))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    # A follow-up after a decline points at the declined request.
    previous_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leave_request.id"))
    # "Mit Tausch beantragen": the extra weekend duty the requester commits to (C1-checked).
    trade_off: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class LeaveCheck(Base):
    """M5: a background check whether a leave is coverable, and the trade-off C1 found."""

    __tablename__ = "leave_check"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','done','failed')", name="status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
