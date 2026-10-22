"""Audit hash chain (tighten): ``chain_key``, ``seq``, ``prev_hash`` and ``hash`` are required.

Safe in the same release as 0007 because every write path goes through
``dienstpilot.audit.service.record`` (or the seed loader), which sets all four, and 0007 chained
every existing row. The migration fails, instead of guessing, if a row without a hash is left.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23 09:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (("chain_key", 40), ("seq", None), ("prev_hash", 64), ("hash", 64))


def upgrade() -> None:
    left = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM audit.event WHERE seq IS NULL OR hash IS NULL"))
        .scalar_one()
    )
    if left:
        raise RuntimeError(f"{left} audit events are not chained; run 0007 first")
    for name, length in COLUMNS:
        type_ = sa.BigInteger() if length is None else sa.String(length=length)
        op.alter_column("event", name, existing_type=type_, nullable=False, schema="audit")


def downgrade() -> None:
    for name, length in COLUMNS:
        type_ = sa.BigInteger() if length is None else sa.String(length=length)
        op.alter_column("event", name, existing_type=type_, nullable=True, schema="audit")
