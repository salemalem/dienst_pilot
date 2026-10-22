"""Seed the audit trail with events derived from the seeded history, and chain them."""

from typing import Any

from sqlalchemy import Connection, Table, insert

from dienstpilot.audit import chain, models  # noqa: F401  (registers the tables)
from dienstpilot.audit.models import ChainHead, Event
from dienstpilot.shared.db import AuditBase as Base

TABLES: list[Table] = list(Base.metadata.sorted_tables)


def _order(e: dict[str, Any]) -> tuple[Any, ...]:
    """Return a total order that does not depend on how the history was assembled."""
    return (e["occurred_at"], e["action"], str(e["subject_id"]), str(e["staff_id"]), str(e["id"]))


def chain_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the events in a fixed order with ``chain_key``, ``seq`` and the hashes filled in."""
    out = []
    state: dict[str, tuple[int, str]] = {}
    for e in sorted(events, key=_order):
        key = chain.chain_key(e["department_id"])
        seq, prev = state.get(key, (0, chain.GENESIS))
        seq += 1
        digest = chain.link(
            prev,
            chain.canonical(
                chain=key,
                seq=seq,
                event_id=e["id"],
                occurred_at=e["occurred_at"],
                department_id=e["department_id"],
                actor_user_id=e["actor_user_id"],
                actor_label=e["actor_label"],
                action=e["action"],
                subject_type=e["subject_type"],
                subject_id=e["subject_id"],
                staff_id=e["staff_id"],
                payload=chain.normalise_payload(e["payload"]),
            ),
        )
        state[key] = (seq, digest)
        out.append(
            {
                **e,
                "payload": chain.normalise_payload(e["payload"]),
                "chain_key": key,
                "seq": seq,
                "prev_hash": prev,
                "hash": digest,
            }
        )
    return out


def load_events(conn: Connection, events: list[dict[str, Any]]) -> int:
    """Chain the prepared events deterministically and insert them in batches."""
    chained = chain_events(events)
    for i in range(0, len(chained), 5000):
        conn.execute(insert(Event), chained[i : i + 5000])
    heads: dict[str, dict[str, Any]] = {}
    for e in chained:
        heads[e["chain_key"]] = {
            "chain_key": e["chain_key"],
            "head_seq": e["seq"],
            "head_hash": e["hash"],
        }
    if heads:
        conn.execute(insert(ChainHead), list(heads.values()))
    return len(chained)
