"""Planning: roster runs (with the versions behind them), variants, assignments, approvals."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import PlanningBase as Base


class RosterRun(Base):
    """One planning run for a month and the versions that produced it."""

    __tablename__ = "roster_run"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    roster_month: Mapped[date] = mapped_column(Date, index=True)
    rule_set_version: Mapped[str] = mapped_column(String(20))
    planner_kind: Mapped[str] = mapped_column(String(40))
    generator_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RosterVariant(Base):
    """A complete roster proposal of a run."""

    __tablename__ = "roster_variant"
    __table_args__ = (CheckConstraint("status IN ('draft','published')", name="status"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roster_run.id"), index=True)
    label: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(10))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Assignment(Base):
    """A physician holds a shift on a date in a variant."""

    __tablename__ = "assignment"
    __table_args__ = (Index("ix_assignment_staff_date", "staff_id", "date"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roster_variant.id"), index=True)
    staff_id: Mapped[uuid.UUID]
    date: Mapped[date] = mapped_column(Date, index=True)
    shift_type: Mapped[str] = mapped_column(String(20))


class Approval(Base):
    """The planner's approval of a variant (or a policy approval the planner configured)."""

    __tablename__ = "approval"
    __table_args__ = (CheckConstraint("kind IN ('planner','policy')", name="kind"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roster_variant.id"), unique=True)
    approved_by: Mapped[uuid.UUID]
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(10))
