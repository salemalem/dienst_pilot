"""Operations: absences, shift swaps and cover cascades.

Sickness is stored as status and dates only; there is no diagnosis field anywhere.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import OperationsBase as Base


class Absence(Base):
    """An absence (sick) with dates. Colleagues see only "absent"."""

    __tablename__ = "absence"
    __table_args__ = (CheckConstraint("category IN ('sick')", name="category"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(10))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SwapOffer(Base):
    """A physician offers a published shift; a colleague may take it over."""

    __tablename__ = "swap_offer"
    __table_args__ = (
        CheckConstraint("status IN ('accepted','expired','rejected')", name="status"),
        CheckConstraint("approval IN ('planner','policy')", name="approval"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    offered_by: Mapped[uuid.UUID]
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None]
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10))
    approval: Mapped[str] = mapped_column(String(10))


class CoverCascade(Base):
    """The search for cover after a sick report, and its outcome."""

    __tablename__ = "cover_cascade"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('covered','escalated_overtime','locum','unfilled')", name="outcome"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    absence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("absence.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(20))
    covered_by: Mapped[uuid.UUID | None]


class CoverOffer(Base):
    """One colleague asked in a cascade, and the answer."""

    __tablename__ = "cover_offer"
    __table_args__ = (
        CheckConstraint("response IN ('accepted','declined','no_response')", name="response"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    cascade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cover_cascade.id"), index=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(index=True)
    rank: Mapped[int]
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response: Mapped[str] = mapped_column(String(15))
