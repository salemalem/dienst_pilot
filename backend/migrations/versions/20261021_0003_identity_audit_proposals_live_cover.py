"""API phase: identity and audit schemas, proposals, live cover cascades (expand-only).

New schemas identity and audit; planning.proposal; operations columns for open cascades,
planner decisions on swaps and cover-offer deadlines. CHECK constraints are widened, never
narrowed, so the seeded rows stay valid

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21 09:57:40.123022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_SCHEMAS = ("identity", "audit")


def upgrade() -> None:
    for schema in NEW_SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.create_table(
        "proposal",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("roster_month", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("source IN ('copilot','planner')", name=op.f("ck_proposal_source")),
        sa.CheckConstraint(
            "status IN ('open','accepted','dismissed')", name=op.f("ck_proposal_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposal")),
        schema="planning",
    )
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("persona_key", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "role IN ('staff','staff_plus','planner','oversight','admin')",
            name=op.f("ck_user_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("persona_key", name=op.f("uq_user_persona_key")),
        sa.UniqueConstraint("staff_id", name=op.f("uq_user_staff_id")),
        schema="identity",
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("theme", sa.String(length=5), nullable=False),
        sa.Column("notifications", sa.Boolean(), nullable=False),
        sa.Column("calendar_sync", sa.Boolean(), nullable=False),
        sa.Column("preference_suggestions", sa.Boolean(), nullable=False),
        sa.CheckConstraint("language IN ('de','en')", name=op.f("ck_user_settings_language")),
        sa.CheckConstraint("theme IN ('auto','light','dark')", name=op.f("ck_user_settings_theme")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["identity.user.id"], name=op.f("fk_user_settings_user_id_user")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_settings")),
        schema="identity",
    )
    op.create_table(
        "event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_label", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event")),
        schema="audit",
    )
    op.create_index(
        op.f("ix_audit_event_action"), "event", ["action"], unique=False, schema="audit"
    )
    op.create_index(
        op.f("ix_audit_event_staff_id"), "event", ["staff_id"], unique=False, schema="audit"
    )
    op.create_index("ix_event_occurred_at", "event", ["occurred_at"], unique=False, schema="audit")
    op.add_column(
        "cover_cascade",
        sa.Column("status", sa.String(length=20), server_default="closed", nullable=False),
        schema="operations",
    )
    op.add_column(
        "cover_cascade",
        sa.Column("escalation_reason", sa.String(length=40), nullable=True),
        schema="operations",
    )
    op.add_column(
        "cover_cascade",
        sa.Column("candidate_queue", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="operations",
    )
    op.alter_column(
        "cover_cascade",
        "closed_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        schema="operations",
    )
    op.alter_column(
        "cover_cascade",
        "outcome",
        existing_type=sa.VARCHAR(length=20),
        nullable=True,
        schema="operations",
    )
    op.add_column(
        "cover_offer",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        schema="operations",
    )
    op.add_column(
        "swap_offer",
        sa.Column("escalation_reason", sa.String(length=40), nullable=True),
        schema="operations",
    )
    op.add_column(
        "swap_offer", sa.Column("decided_by", sa.Uuid(), nullable=True), schema="operations"
    )
    op.add_column(
        "swap_offer",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema="operations",
    )
    op.add_column(
        "swap_offer", sa.Column("decision_reason", sa.Text(), nullable=True), schema="operations"
    )
    op.alter_column(
        "swap_offer",
        "status",
        existing_type=sa.VARCHAR(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
        schema="operations",
    )
    op.alter_column(
        "swap_offer",
        "approval",
        existing_type=sa.VARCHAR(length=10),
        nullable=True,
        schema="operations",
    )
    _replace_check(
        "swap_offer",
        "status",
        "status IN ('open','pending_approval','approved','declined',"
        " 'accepted','expired','rejected')",
    )
    _replace_check(
        "cover_offer", "response", "response IN ('pending','accepted','declined','no_response')"
    )
    op.create_check_constraint(
        "ck_cover_cascade_status",
        "cover_cascade",
        "status IN ('open','pending_approval','closed')",
        schema="operations",
    )


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(f"ck_{table}_{name}", table, schema="operations", type_="check")
    op.create_check_constraint(f"ck_{table}_{name}", table, condition, schema="operations")


def downgrade() -> None:
    op.drop_constraint(
        "ck_cover_cascade_status", "cover_cascade", schema="operations", type_="check"
    )
    _replace_check("cover_offer", "response", "response IN ('accepted','declined','no_response')")
    _replace_check("swap_offer", "status", "status IN ('accepted','expired','rejected')")
    op.alter_column(
        "swap_offer",
        "approval",
        existing_type=sa.VARCHAR(length=10),
        nullable=False,
        schema="operations",
    )
    op.alter_column(
        "swap_offer",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.VARCHAR(length=10),
        existing_nullable=False,
        schema="operations",
    )
    op.drop_column("swap_offer", "decision_reason", schema="operations")
    op.drop_column("swap_offer", "decided_at", schema="operations")
    op.drop_column("swap_offer", "decided_by", schema="operations")
    op.drop_column("swap_offer", "escalation_reason", schema="operations")
    op.drop_column("cover_offer", "deadline_at", schema="operations")
    op.alter_column(
        "cover_cascade",
        "outcome",
        existing_type=sa.VARCHAR(length=20),
        nullable=False,
        schema="operations",
    )
    op.alter_column(
        "cover_cascade",
        "closed_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        schema="operations",
    )
    op.drop_column("cover_cascade", "candidate_queue", schema="operations")
    op.drop_column("cover_cascade", "escalation_reason", schema="operations")
    op.drop_column("cover_cascade", "status", schema="operations")
    op.drop_index("ix_event_occurred_at", table_name="event", schema="audit")
    op.drop_index(op.f("ix_audit_event_staff_id"), table_name="event", schema="audit")
    op.drop_index(op.f("ix_audit_event_action"), table_name="event", schema="audit")
    op.drop_table("event", schema="audit")
    op.drop_table("user_settings", schema="identity")
    op.drop_table("user", schema="identity")
    op.drop_table("proposal", schema="planning")
    for schema in reversed(NEW_SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema}")
