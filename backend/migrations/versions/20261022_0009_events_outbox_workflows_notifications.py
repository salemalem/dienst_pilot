"""Events outbox, durable workflows and stored notifications (expand-only: new schemas).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-22 17:01:33.821152
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_SCHEMAS = ("events", "workflow", "notifications")


def upgrade() -> None:
    for schema in NEW_SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.create_table(
        "outbox",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("relayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stream_id", sa.String(length=40), nullable=True),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_outbox")),
        sa.UniqueConstraint("event_id", name=op.f("uq_outbox_event_id")),
        schema="events",
    )
    op.create_index(
        "ix_outbox_unrelayed",
        "outbox",
        ["seq"],
        unique=False,
        schema="events",
        postgresql_where="relayed_at IS NULL",
    )
    op.create_table(
        "processed",
        sa.Column("consumer", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("consumer", "event_id", name=op.f("pk_processed")),
        schema="events",
    )
    op.create_table(
        "instance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instance")),
        schema="workflow",
    )
    op.create_index(
        "uq_instance_kind_key", "instance", ["kind", "key"], unique=True, schema="workflow"
    )
    op.create_table(
        "timer",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_timer")),
        schema="workflow",
    )
    op.create_index(
        "ix_timer_due",
        "timer",
        ["due_at", "id"],
        unique=False,
        schema="workflow",
        postgresql_where=sa.text("fired_at IS NULL AND cancelled_at IS NULL AND failed_at IS NULL"),
    )
    op.create_index("uq_timer_kind_key", "timer", ["kind", "key"], unique=True, schema="workflow")
    op.create_table(
        "notification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification")),
        schema="notifications",
    )
    op.create_index(
        op.f("ix_notifications_notification_staff_id"),
        "notification",
        ["staff_id"],
        unique=False,
        schema="notifications",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notifications_notification_staff_id"),
        table_name="notification",
        schema="notifications",
    )
    op.drop_table("notification", schema="notifications")
    op.drop_index("uq_timer_kind_key", table_name="timer", schema="workflow")
    op.drop_index(
        "ix_timer_due",
        table_name="timer",
        schema="workflow",
        postgresql_where=sa.text("fired_at IS NULL AND cancelled_at IS NULL AND failed_at IS NULL"),
    )
    op.drop_table("timer", schema="workflow")
    op.drop_index("uq_instance_kind_key", table_name="instance", schema="workflow")
    op.drop_table("instance", schema="workflow")
    op.drop_table("processed", schema="events")
    op.drop_index(
        "ix_outbox_unrelayed",
        table_name="outbox",
        schema="events",
        postgresql_where="relayed_at IS NULL",
    )
    op.drop_table("outbox", schema="events")
    for schema in reversed(NEW_SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema}")
