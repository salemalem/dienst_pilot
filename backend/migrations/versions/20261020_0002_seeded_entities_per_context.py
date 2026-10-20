"""Seeded entities, one schema per bounded context (expand-only).

Creates the organization, requests, planning and operations schemas and their tables. There
are no foreign keys across schemas; cross-context references are plain UUIDs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEMAS = ("organization", "requests", "planning", "operations")


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.create_table(
        "department",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short_name", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_department")),
        schema="organization",
    )
    op.create_table(
        "holiday",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name_de", sa.String(length=80), nullable=False),
        sa.Column("name_en", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("date", name=op.f("pk_holiday")),
        schema="organization",
    )
    op.create_table(
        "qualification",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name_de", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_qualification")),
        schema="organization",
    )
    op.create_table(
        "rule_set",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("change_note_de", sa.String(length=300), nullable=False),
        sa.Column("change_note_en", sa.String(length=300), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_set")),
        sa.UniqueConstraint("version", name=op.f("uq_rule_set_version")),
        schema="organization",
    )
    op.create_table(
        "school_holiday",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("name_de", sa.String(length=80), nullable=False),
        sa.Column("name_en", sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_school_holiday")),
        schema="organization",
    )
    op.create_table(
        "shift_type",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("letter_de", sa.String(length=2), nullable=False),
        sa.Column("letter_en", sa.String(length=2), nullable=False),
        sa.Column("name_de", sa.String(length=80), nullable=False),
        sa.Column("name_en", sa.String(length=80), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("ends_next_day", sa.Boolean(), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("net_hours", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("counts_as_working_time", sa.Boolean(), nullable=False),
        sa.Column("burden_weight", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.CheckConstraint(
            "kind IN ('work','on_call','on_call_home','leave')", name=op.f("ck_shift_type_kind")
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_shift_type")),
        schema="organization",
    )
    op.create_table(
        "shift_demand",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shift_type", sa.String(length=20), nullable=False),
        sa.Column("qualification", sa.String(length=40), nullable=False),
        sa.Column("required_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shift_type"],
            ["organization.shift_type.code"],
            name=op.f("fk_shift_demand_shift_type_shift_type"),
        ),
        sa.PrimaryKeyConstraint(
            "date", "shift_type", "qualification", name=op.f("pk_shift_demand")
        ),
        schema="organization",
    )
    op.create_table(
        "staff",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["organization.department.id"],
            name=op.f("fk_staff_department_id_department"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff")),
        schema="organization",
    )
    op.create_table(
        "contract",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("title_de", sa.String(length=80), nullable=False),
        sa.Column("title_en", sa.String(length=80), nullable=False),
        sa.Column("weekly_hours", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "role IN ('chefaerztin','oberarzt','facharzt','assistenzarzt')",
            name=op.f("ck_contract_role"),
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"], ["organization.staff.id"], name=op.f("fk_contract_staff_id_staff")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contract")),
        schema="organization",
    )
    op.create_index(
        op.f("ix_organization_contract_staff_id"),
        "contract",
        ["staff_id"],
        unique=False,
        schema="organization",
    )
    op.create_table(
        "staff_qualification",
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("qualification", sa.String(length=40), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["qualification"],
            ["organization.qualification.code"],
            name=op.f("fk_staff_qualification_qualification_qualification"),
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["organization.staff.id"],
            name=op.f("fk_staff_qualification_staff_id_staff"),
        ),
        sa.PrimaryKeyConstraint(
            "staff_id", "qualification", "valid_from", name=op.f("pk_staff_qualification")
        ),
        schema="organization",
    )
    op.create_table(
        "staff_rotation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(length=80), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["staff_id"], ["organization.staff.id"], name=op.f("fk_staff_rotation_staff_id_staff")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_rotation")),
        schema="organization",
    )
    op.create_index(
        op.f("ix_organization_staff_rotation_staff_id"),
        "staff_rotation",
        ["staff_id"],
        unique=False,
        schema="organization",
    )
    op.create_table(
        "leave_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decision_reason_code", sa.String(length=40), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "decision_reason IS NULL OR status = 'declined'",
            name=op.f("ck_leave_request_reason_only_for_declines"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','declined')", name=op.f("ck_leave_request_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_request")),
        schema="requests",
    )
    op.create_index(
        op.f("ix_requests_leave_request_staff_id"),
        "leave_request",
        ["staff_id"],
        unique=False,
        schema="requests",
    )
    op.create_table(
        "request_window",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("roster_month", sa.Date(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('open','closed')", name=op.f("ck_request_window_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_window")),
        sa.UniqueConstraint("roster_month", name=op.f("uq_request_window_roster_month")),
        schema="requests",
    )
    op.create_table(
        "preference",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("window_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("shift_type", sa.String(length=20), nullable=True),
        sa.Column("important", sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind IN ('unavailable','wish_work')", name=op.f("ck_preference_kind")),
        sa.ForeignKeyConstraint(
            ["window_id"],
            ["requests.request_window.id"],
            name=op.f("fk_preference_window_id_request_window"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preference")),
        schema="requests",
    )
    op.create_index(
        op.f("ix_requests_preference_staff_id"),
        "preference",
        ["staff_id"],
        unique=False,
        schema="requests",
    )
    op.create_index(
        op.f("ix_requests_preference_window_id"),
        "preference",
        ["window_id"],
        unique=False,
        schema="requests",
    )
    op.create_table(
        "window_response",
        sa.Column("window_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["window_id"],
            ["requests.request_window.id"],
            name=op.f("fk_window_response_window_id_request_window"),
        ),
        sa.PrimaryKeyConstraint("window_id", "staff_id", name=op.f("pk_window_response")),
        schema="requests",
    )
    op.create_table(
        "roster_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("roster_month", sa.Date(), nullable=False),
        sa.Column("rule_set_version", sa.String(length=20), nullable=False),
        sa.Column("planner_kind", sa.String(length=40), nullable=False),
        sa.Column("generator_version", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roster_run")),
        schema="planning",
    )
    op.create_index(
        op.f("ix_planning_roster_run_roster_month"),
        "roster_run",
        ["roster_month"],
        unique=False,
        schema="planning",
    )
    op.create_table(
        "roster_variant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft','published')", name=op.f("ck_roster_variant_status")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["planning.roster_run.id"], name=op.f("fk_roster_variant_run_id_roster_run")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roster_variant")),
        schema="planning",
    )
    op.create_index(
        op.f("ix_planning_roster_variant_run_id"),
        "roster_variant",
        ["run_id"],
        unique=False,
        schema="planning",
    )
    op.create_table(
        "approval",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.CheckConstraint("kind IN ('planner','policy')", name=op.f("ck_approval_kind")),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["planning.roster_variant.id"],
            name=op.f("fk_approval_variant_id_roster_variant"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval")),
        sa.UniqueConstraint("variant_id", name=op.f("uq_approval_variant_id")),
        schema="planning",
    )
    op.create_table(
        "assignment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shift_type", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["planning.roster_variant.id"],
            name=op.f("fk_assignment_variant_id_roster_variant"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment")),
        schema="planning",
    )
    op.create_index(
        "ix_assignment_staff_date",
        "assignment",
        ["staff_id", "date"],
        unique=False,
        schema="planning",
    )
    op.create_index(
        op.f("ix_planning_assignment_date"), "assignment", ["date"], unique=False, schema="planning"
    )
    op.create_index(
        op.f("ix_planning_assignment_variant_id"),
        "assignment",
        ["variant_id"],
        unique=False,
        schema="planning",
    )
    op.create_table(
        "absence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("category IN ('sick')", name=op.f("ck_absence_category")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_absence")),
        schema="operations",
    )
    op.create_index(
        op.f("ix_operations_absence_staff_id"),
        "absence",
        ["staff_id"],
        unique=False,
        schema="operations",
    )
    op.create_table(
        "swap_offer",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("offered_by", sa.Uuid(), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("approval", sa.String(length=10), nullable=False),
        sa.CheckConstraint("approval IN ('planner','policy')", name=op.f("ck_swap_offer_approval")),
        sa.CheckConstraint(
            "status IN ('accepted','expired','rejected')", name=op.f("ck_swap_offer_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_swap_offer")),
        schema="operations",
    )
    op.create_index(
        op.f("ix_operations_swap_offer_assignment_id"),
        "swap_offer",
        ["assignment_id"],
        unique=False,
        schema="operations",
    )
    op.create_table(
        "cover_cascade",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("absence_id", sa.Uuid(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("covered_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('covered','escalated_overtime','locum','unfilled')",
            name=op.f("ck_cover_cascade_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["absence_id"],
            ["operations.absence.id"],
            name=op.f("fk_cover_cascade_absence_id_absence"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cover_cascade")),
        schema="operations",
    )
    op.create_index(
        op.f("ix_operations_cover_cascade_absence_id"),
        "cover_cascade",
        ["absence_id"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        op.f("ix_operations_cover_cascade_assignment_id"),
        "cover_cascade",
        ["assignment_id"],
        unique=False,
        schema="operations",
    )
    op.create_table(
        "cover_offer",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cascade_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", sa.String(length=15), nullable=False),
        sa.CheckConstraint(
            "response IN ('accepted','declined','no_response')",
            name=op.f("ck_cover_offer_response"),
        ),
        sa.ForeignKeyConstraint(
            ["cascade_id"],
            ["operations.cover_cascade.id"],
            name=op.f("fk_cover_offer_cascade_id_cover_cascade"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cover_offer")),
        schema="operations",
    )
    op.create_index(
        op.f("ix_operations_cover_offer_cascade_id"),
        "cover_offer",
        ["cascade_id"],
        unique=False,
        schema="operations",
    )
    op.create_index(
        op.f("ix_operations_cover_offer_staff_id"),
        "cover_offer",
        ["staff_id"],
        unique=False,
        schema="operations",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_operations_cover_offer_staff_id"), table_name="cover_offer", schema="operations"
    )
    op.drop_index(
        op.f("ix_operations_cover_offer_cascade_id"), table_name="cover_offer", schema="operations"
    )
    op.drop_table("cover_offer", schema="operations")
    op.drop_index(
        op.f("ix_operations_cover_cascade_assignment_id"),
        table_name="cover_cascade",
        schema="operations",
    )
    op.drop_index(
        op.f("ix_operations_cover_cascade_absence_id"),
        table_name="cover_cascade",
        schema="operations",
    )
    op.drop_table("cover_cascade", schema="operations")
    op.drop_index(
        op.f("ix_operations_swap_offer_assignment_id"), table_name="swap_offer", schema="operations"
    )
    op.drop_table("swap_offer", schema="operations")
    op.drop_index(op.f("ix_operations_absence_staff_id"), table_name="absence", schema="operations")
    op.drop_table("absence", schema="operations")
    op.drop_index(
        op.f("ix_planning_assignment_variant_id"), table_name="assignment", schema="planning"
    )
    op.drop_index(op.f("ix_planning_assignment_date"), table_name="assignment", schema="planning")
    op.drop_index("ix_assignment_staff_date", table_name="assignment", schema="planning")
    op.drop_table("assignment", schema="planning")
    op.drop_table("approval", schema="planning")
    op.drop_index(
        op.f("ix_planning_roster_variant_run_id"), table_name="roster_variant", schema="planning"
    )
    op.drop_table("roster_variant", schema="planning")
    op.drop_index(
        op.f("ix_planning_roster_run_roster_month"), table_name="roster_run", schema="planning"
    )
    op.drop_table("roster_run", schema="planning")
    op.drop_table("window_response", schema="requests")
    op.drop_index(
        op.f("ix_requests_preference_window_id"), table_name="preference", schema="requests"
    )
    op.drop_index(
        op.f("ix_requests_preference_staff_id"), table_name="preference", schema="requests"
    )
    op.drop_table("preference", schema="requests")
    op.drop_table("request_window", schema="requests")
    op.drop_index(
        op.f("ix_requests_leave_request_staff_id"), table_name="leave_request", schema="requests"
    )
    op.drop_table("leave_request", schema="requests")
    op.drop_index(
        op.f("ix_organization_staff_rotation_staff_id"),
        table_name="staff_rotation",
        schema="organization",
    )
    op.drop_table("staff_rotation", schema="organization")
    op.drop_table("staff_qualification", schema="organization")
    op.drop_index(
        op.f("ix_organization_contract_staff_id"), table_name="contract", schema="organization"
    )
    op.drop_table("contract", schema="organization")
    op.drop_table("staff", schema="organization")
    op.drop_table("shift_demand", schema="organization")
    op.drop_table("shift_type", schema="organization")
    op.drop_table("school_holiday", schema="organization")
    op.drop_table("rule_set", schema="organization")
    op.drop_table("qualification", schema="organization")
    op.drop_table("holiday", schema="organization")
    op.drop_table("department", schema="organization")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema}")
