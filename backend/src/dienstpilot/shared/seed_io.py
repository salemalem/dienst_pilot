"""Load seed Parquet files into a context's tables (used by each context's seed module)."""

import json
import uuid
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import Connection, Table, Uuid
from sqlalchemy.dialects.postgresql import JSONB

BATCH = 5000


def _converter(table: Table) -> dict[str, Any]:
    conv: dict[str, Any] = {}
    for col in table.columns:
        if isinstance(col.type, Uuid):
            conv[col.name] = lambda v: None if v is None else uuid.UUID(v)
        elif isinstance(col.type, JSONB):
            conv[col.name] = lambda v: None if v is None else json.loads(v)
    return conv


def read_rows(path: Path, table: Table) -> list[dict[str, Any]]:
    """Read one Parquet file as rows for ``table``, converting UUID and JSON columns."""
    df = pl.read_parquet(path)
    missing = {c.name for c in table.columns} ^ set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: columns differ from {table.fullname}: {sorted(missing)}")
    conv = _converter(table)
    rows = df.to_dicts()
    for r in rows:
        for name, f in conv.items():
            r[name] = f(r[name])
    return rows


def load_tables(conn: Connection, root: Path, tables: list[Table]) -> dict[str, int]:
    """Insert every table from ``root/<schema>/<table>.parquet``, in the given order."""
    counts: dict[str, int] = {}
    for table in tables:
        rows = read_rows(root / str(table.schema) / f"{table.name}.parquet", table)
        for i in range(0, len(rows), BATCH):
            conn.execute(table.insert(), rows[i : i + BATCH])
        counts[f"{table.schema}/{table.name}"] = len(rows)
    return counts
