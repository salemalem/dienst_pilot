"""Copilot runs: a question to the planner copilot and its outcome (expand-only, new table).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-25 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed')", name="ck_copilot_run_status"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_copilot_run"),
        schema="planning",
    )


def downgrade() -> None:
    op.drop_table("copilot_run", schema="planning")
