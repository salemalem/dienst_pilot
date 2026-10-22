"""C6: the instant hint of a leave check and whether the solver agreed with it.

Expand-only: four nullable columns on ``requests.leave_check``; code that does not know them is
unaffected, and rows written before this migration simply have no hint.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("hint_outcome", 14),
    ("hint_version", 80),
    ("hint_basis", 5),
    ("agreement", 10),
)


def upgrade() -> None:
    for name, length in COLUMNS:
        op.add_column(
            "leave_check",
            sa.Column(name, sa.String(length=length), nullable=True),
            schema="requests",
        )


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("leave_check", name, schema="requests")
