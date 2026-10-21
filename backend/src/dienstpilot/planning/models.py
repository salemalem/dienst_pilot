"""Planning: roster runs (with the versions behind them), variants, assignments, approvals."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dienstpilot.shared.db import PlanningBase as Base


class RosterRun(Base):
    """One planning run for a month and the versions that produced it."""

    __tablename__ = "roster_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','infeasible','failed')", name="status"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    roster_month: Mapped[date] = mapped_column(Date, index=True)
    rule_set_version: Mapped[str] = mapped_column(String(20))
    planner_kind: Mapped[str] = mapped_column(String(40))
    generator_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Solver runs (C1): who asked, progress, the exact versions and settings, and why it failed.
    status: Mapped[str] = mapped_column(String(12), server_default="done")
    requested_by: Mapped[uuid.UUID | None]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solver_version: Mapped[str | None] = mapped_column(String(20))
    validator_version: Mapped[str | None] = mapped_column(String(20))
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    explanations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)


class RosterVariant(Base):
    """A complete roster proposal of a run."""

    __tablename__ = "roster_variant"
    __table_args__ = (
        CheckConstraint("status IN ('draft','published','discarded')", name="status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roster_run.id"), index=True)
    label: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(10))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile: Mapped[str | None] = mapped_column(String(20))
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    recommended: Mapped[bool] = mapped_column(server_default="false")


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


class Proposal(Base):
    """A suggested roster change for the Planner's inbox. Agents may create proposals only."""

    __tablename__ = "proposal"
    __table_args__ = (
        CheckConstraint("status IN ('open','accepted','dismissed')", name="status"),
        CheckConstraint("source IN ('copilot','planner')", name="source"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    department_id: Mapped[uuid.UUID]
    roster_month: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID]  # the user on whose behalf it was created
    source: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssignmentChange(Base):
    """A Planner's change to a published roster (PROCESS §2: reason required, everyone notified).

    The published assignments stay as approved; changes are applied on top, like swaps.
    """

    __tablename__ = "assignment_change"
    __table_args__ = (
        CheckConstraint("kind IN ('reassign','add','remove')", name="kind"),
        CheckConstraint("length(reason) > 0", name="reason"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    roster_month: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(10))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(index=True)  # None for an added shift
    date: Mapped[date] = mapped_column(Date)
    shift_type: Mapped[str] = mapped_column(String(20))
    staff_before: Mapped[uuid.UUID | None]
    staff_after: Mapped[uuid.UUID | None]
    reason: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID]
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
