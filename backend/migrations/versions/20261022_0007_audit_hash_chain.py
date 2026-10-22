"""Audit hash chain (expand): chain columns, chain head and check tables, backfill.

Adds ``chain_key``, ``seq``, ``prev_hash`` and ``hash`` to ``audit.event`` (nullable here; 0008
makes them required once every write path sets them), lets ``department_id`` be empty for the
system chain, creates ``audit.chain_head`` and ``audit.chain_check``, and chains the rows that
already exist. The backfill order is deterministic: (occurred_at, id) within a department.

The canonical JSON below is a frozen copy of ``dienstpilot.audit.chain`` (format version 1), so
this migration never changes meaning when the application code moves on; a test checks that the
two agree.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23 09:00:00.000000
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GENESIS = "0" * 64


def _id(v: object) -> str | None:
    return None if v is None else str(v).lower()


def _canonical(key: str, seq: int, r: sa.Row[tuple[object, ...]]) -> bytes:
    doc = {
        "v": 1,
        "chain": key,
        "seq": seq,
        "id": _id(r.id),
        "at": r.occurred_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "department_id": _id(r.department_id),
        "actor_user_id": _id(r.actor_user_id),
        "actor": r.actor_label,
        "action": r.action,
        "subject_type": r.subject_type,
        "subject_id": _id(r.subject_id),
        "staff_id": _id(r.staff_id),
        "payload": r.payload,
    }
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def upgrade() -> None:
    for name, length in (("chain_key", 40), ("prev_hash", 64), ("hash", 64)):
        op.add_column(
            "event", sa.Column(name, sa.String(length=length), nullable=True), schema="audit"
        )
    op.add_column("event", sa.Column("seq", sa.BigInteger(), nullable=True), schema="audit")
    op.alter_column("event", "department_id", nullable=True, schema="audit")
    op.create_table(
        "chain_head",
        sa.Column("chain_key", sa.String(length=40), nullable=False),
        sa.Column("head_seq", sa.BigInteger(), nullable=False),
        sa.Column("head_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("chain_key", name=op.f("pk_chain_head")),
        schema="audit",
    )
    op.create_table(
        "chain_check",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chain_key", sa.String(length=40), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger", sa.String(length=10), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("rows", sa.BigInteger(), nullable=False),
        sa.Column("head_seq", sa.BigInteger(), nullable=False),
        sa.Column("head_hash", sa.String(length=64), nullable=False),
        sa.Column("first_bad_seq", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chain_check")),
        schema="audit",
    )
    op.create_index(
        op.f("ix_audit_chain_check_chain_key"), "chain_check", ["chain_key"], schema="audit"
    )
    _backfill()
    op.create_index(
        "uq_event_chain_seq", "event", ["chain_key", "seq"], unique=True, schema="audit"
    )


def _backfill() -> None:
    conn = op.get_bind()
    event = sa.table(
        "event",
        sa.column("id"),
        sa.column("occurred_at"),
        sa.column("department_id"),
        sa.column("actor_user_id"),
        sa.column("actor_label"),
        sa.column("action"),
        sa.column("subject_type"),
        sa.column("subject_id"),
        sa.column("staff_id"),
        sa.column("payload"),
        sa.column("chain_key"),
        sa.column("seq"),
        sa.column("prev_hash"),
        sa.column("hash"),
        schema="audit",
    )
    head = sa.table(
        "chain_head",
        sa.column("chain_key"),
        sa.column("head_seq"),
        sa.column("head_hash"),
        schema="audit",
    )
    keys = [
        str(k) if k is not None else "system"
        for (k,) in conn.execute(sa.select(event.c.department_id).distinct())
    ]
    for key in sorted(keys):
        cond = (
            event.c.department_id.is_(None)
            if key == "system"
            else event.c.department_id == sa.cast(key, sa.Uuid())
        )
        prev, seq, updates = GENESIS, 0, []
        for r in conn.execute(
            sa.select(event).where(cond).order_by(event.c.occurred_at, event.c.id)
        ):
            seq += 1
            digest = hashlib.sha256(prev.encode("ascii") + _canonical(key, seq, r)).hexdigest()
            updates.append(
                {"b_id": r.id, "b_key": key, "b_seq": seq, "b_prev": prev, "b_hash": digest}
            )
            prev = digest
        for i in range(0, len(updates), 2000):
            conn.execute(
                event.update()
                .where(event.c.id == sa.bindparam("b_id"))
                .values(
                    chain_key=sa.bindparam("b_key"),
                    seq=sa.bindparam("b_seq"),
                    prev_hash=sa.bindparam("b_prev"),
                    hash=sa.bindparam("b_hash"),
                ),
                updates[i : i + 2000],
            )
        if seq:
            conn.execute(head.insert().values(chain_key=key, head_seq=seq, head_hash=prev))


def downgrade() -> None:
    op.drop_index("uq_event_chain_seq", table_name="event", schema="audit")
    op.drop_table("chain_check", schema="audit")
    op.drop_table("chain_head", schema="audit")
    op.execute("DELETE FROM audit.event WHERE department_id IS NULL")
    op.alter_column("event", "department_id", nullable=False, schema="audit")
    for name in ("seq", "hash", "prev_hash", "chain_key"):
        op.drop_column("event", name, schema="audit")
