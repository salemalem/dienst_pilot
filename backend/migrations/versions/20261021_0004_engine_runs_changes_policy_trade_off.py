"""Engine phase: solver runs, published-roster changes, auto-approval policy, leave trade-off
and leave checks.

Expand-only: new tables and nullable or defaulted columns; CHECK constraints widened

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21 11:48:07.525375
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leave_check",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed')", name=op.f("ck_leave_check_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_check")),
        schema="requests",
    )
    op.create_index(
        op.f("ix_requests_leave_check_staff_id"),
        "leave_check",
        ["staff_id"],
        unique=False,
        schema="requests",
    )
    op.create_table(
        "assignment_change",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("roster_month", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shift_type", sa.String(length=20), nullable=False),
        sa.Column("staff_before", sa.Uuid(), nullable=True),
        sa.Column("staff_after", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('reassign','add','remove')", name=op.f("ck_assignment_change_kind")
        ),
        sa.CheckConstraint("length(reason) > 0", name=op.f("ck_assignment_change_reason")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_change")),
        schema="planning",
    )
    op.create_index(
        op.f("ix_planning_assignment_change_assignment_id"),
        "assignment_change",
        ["assignment_id"],
        unique=False,
        schema="planning",
    )
    op.create_index(
        op.f("ix_planning_assignment_change_roster_month"),
        "assignment_change",
        ["roster_month"],
        unique=False,
        schema="planning",
    )
    op.create_table(
        "policy",
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("auto_approve_swaps", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("auto_approve_cover", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("department_id", name=op.f("pk_policy")),
        schema="operations",
    )
    op.add_column(
        "cover_cascade",
        sa.Column("approval", sa.String(length=10), nullable=True),
        schema="operations",
    )
    op.add_column(
        "swap_offer",
        sa.Column("counter_assignment_id", sa.Uuid(), nullable=True),
        schema="operations",
    )
    op.add_column(
        "roster_run",
        sa.Column("status", sa.String(length=12), server_default="done", nullable=False),
        schema="planning",
    )
    op.add_column(
        "roster_run", sa.Column("requested_by", sa.Uuid(), nullable=True), schema="planning"
    )
    op.add_column(
        "roster_run",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        schema="planning",
    )
    op.add_column(
        "roster_run",
        sa.Column("solver_version", sa.String(length=20), nullable=True),
        schema="planning",
    )
    op.add_column(
        "roster_run",
        sa.Column("validator_version", sa.String(length=20), nullable=True),
        schema="planning",
    )
    op.add_column(
        "roster_run",
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="planning",
    )
    op.add_column(
        "roster_run",
        sa.Column("explanations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="planning",
    )
    op.add_column("roster_run", sa.Column("error", sa.Text(), nullable=True), schema="planning")
    op.add_column(
        "roster_variant",
        sa.Column("profile", sa.String(length=20), nullable=True),
        schema="planning",
    )
    op.add_column(
        "roster_variant",
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="planning",
    )
    op.add_column(
        "roster_variant",
        sa.Column("recommended", sa.Boolean(), server_default="false", nullable=False),
        schema="planning",
    )
    op.add_column(
        "leave_request",
        sa.Column("trade_off", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="requests",
    )
    op.create_check_constraint(
        "ck_roster_run_status",
        "roster_run",
        "status IN ('queued','running','done','infeasible','failed')",
        schema="planning",
    )
    op.drop_constraint(
        "ck_roster_variant_status", "roster_variant", schema="planning", type_="check"
    )
    op.create_check_constraint(
        "ck_roster_variant_status",
        "roster_variant",
        "status IN ('draft','published','discarded')",
        schema="planning",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_roster_variant_status", "roster_variant", schema="planning", type_="check"
    )
    op.create_check_constraint(
        "ck_roster_variant_status",
        "roster_variant",
        "status IN ('draft','published')",
        schema="planning",
    )
    op.drop_constraint("ck_roster_run_status", "roster_run", schema="planning", type_="check")
    op.drop_column("leave_request", "trade_off", schema="requests")
    op.drop_column("roster_variant", "recommended", schema="planning")
    op.drop_column("roster_variant", "metrics", schema="planning")
    op.drop_column("roster_variant", "profile", schema="planning")
    op.drop_column("roster_run", "error", schema="planning")
    op.drop_column("roster_run", "explanations", schema="planning")
    op.drop_column("roster_run", "config", schema="planning")
    op.drop_column("roster_run", "validator_version", schema="planning")
    op.drop_column("roster_run", "solver_version", schema="planning")
    op.drop_column("roster_run", "finished_at", schema="planning")
    op.drop_column("roster_run", "requested_by", schema="planning")
    op.drop_column("roster_run", "status", schema="planning")
    op.drop_column("swap_offer", "counter_assignment_id", schema="operations")
    op.drop_column("cover_cascade", "approval", schema="operations")
    op.drop_table("policy", schema="operations")
    op.drop_index(
        op.f("ix_planning_assignment_change_roster_month"),
        table_name="assignment_change",
        schema="planning",
    )
    op.drop_index(
        op.f("ix_planning_assignment_change_assignment_id"),
        table_name="assignment_change",
        schema="planning",
    )
    op.drop_table("assignment_change", schema="planning")
    op.drop_index(
        op.f("ix_requests_leave_check_staff_id"), table_name="leave_check", schema="requests"
    )
    op.drop_table("leave_check", schema="requests")
