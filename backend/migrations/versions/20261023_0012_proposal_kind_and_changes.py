"""Proposals carry a kind and, optionally, the changes they suggest (expand-only).

``kind``: ``change`` (default; every existing row) or ``announcement`` (a draft text the agents
may write; nothing sends it). ``changes``: the suggested roster changes as JSON, for the Planner to
review; nothing applies them.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-23 09:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proposal",
        sa.Column("kind", sa.String(length=12), server_default="change", nullable=False),
        schema="planning",
    )
    op.add_column(
        "proposal",
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="planning",
    )
    op.create_check_constraint(
        "ck_proposal_kind", "proposal", "kind IN ('change','announcement')", schema="planning"
    )


def downgrade() -> None:
    op.drop_constraint("ck_proposal_kind", "proposal", schema="planning")
    op.drop_column("proposal", "changes", schema="planning")
    op.drop_column("proposal", "kind", schema="planning")
