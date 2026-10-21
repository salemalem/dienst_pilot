"""Seed the audit trail with events derived from the seeded history (the hash chain is Phase 9)."""

from typing import Any

from sqlalchemy import Connection, Table, insert

from dienstpilot.audit import models  # noqa: F401  (registers the tables)
from dienstpilot.audit.models import Event
from dienstpilot.shared.db import AuditBase as Base

TABLES: list[Table] = list(Base.metadata.sorted_tables)


def load_events(conn: Connection, events: list[dict[str, Any]]) -> int:
    """Insert prepared events in batches."""
    for i in range(0, len(events), 5000):
        conn.execute(insert(Event), events[i : i + 5000])
    return len(events)
