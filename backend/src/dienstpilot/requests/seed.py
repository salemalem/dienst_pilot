"""Public seed interface of the requests context."""

from pathlib import Path

from sqlalchemy import Connection, Table

from dienstpilot.requests import models  # noqa: F401  (registers the tables)
from dienstpilot.shared.db import RequestsBase as Base
from dienstpilot.shared.seed_io import load_tables

# Dependency order (parents before children), as SQLAlchemy sorts them by foreign key.
TABLES: list[Table] = list(Base.metadata.sorted_tables)


def load(conn: Connection, root: Path) -> dict[str, int]:
    """Load this context's tables from the seed directory; return row counts."""
    return load_tables(conn, root, TABLES)
