"""Month-end reports (expand-only: new schema ``fairness`` with one table).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-22 17:05:58.024947
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fairness")
    op.create_table(
        "month_report",
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("roster_month", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(), nullable=True),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("status IN ('prepared','closed')", name=op.f("ck_month_report_status")),
        sa.PrimaryKeyConstraint("department_id", "roster_month", name=op.f("pk_month_report")),
        schema="fairness",
    )


def downgrade() -> None:
    op.drop_table("month_report", schema="fairness")
    op.execute("DROP SCHEMA IF EXISTS fairness")
