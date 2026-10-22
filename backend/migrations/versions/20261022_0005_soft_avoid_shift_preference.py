"""Soft per-shift preference: a request-window entry may now say "rather not this shift".

Expand-only: the CHECK constraint on ``requests.preference.kind`` is widened by one value; no
column and no row changes, and code that does not know the value is unaffected.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22 12:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_preference_kind", "preference", schema="requests", type_="check")
    op.create_check_constraint(
        op.f("ck_preference_kind"),
        "preference",
        "kind IN ('unavailable','wish_work','avoid_shift')",
        schema="requests",
    )


def downgrade() -> None:
    op.execute("DELETE FROM requests.preference WHERE kind = 'avoid_shift'")
    op.drop_constraint("ck_preference_kind", "preference", schema="requests", type_="check")
    op.create_check_constraint(
        op.f("ck_preference_kind"),
        "preference",
        "kind IN ('unavailable','wish_work')",
        schema="requests",
    )
