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


def parents_first(rows: list[dict[str, Any]], table: Table) -> list[dict[str, Any]]:
    """Order rows so a row referencing another row of the same table comes after it."""
    self_refs = [
        (fk.parent.name, fk.column.name) for fk in table.foreign_keys if fk.column.table is table
    ]
    if not self_refs:
        return rows
    placed: set[Any] = set()
    ordered: list[dict[str, Any]] = []
    pending = rows
    while pending:
        ready = [r for r in pending if all(r[c] is None or r[c] in placed for c, _ in self_refs)]
        if not ready:
            raise ValueError(f"{table.fullname}: rows reference rows that do not exist")
        for r in ready:
            placed.update(r[target] for _, target in self_refs)
        ordered += ready
        ready_ids = {id(r) for r in ready}
        pending = [r for r in pending if id(r) not in ready_ids]
    return ordered


def load_tables(conn: Connection, root: Path, tables: list[Table]) -> dict[str, int]:
    """Insert every table from ``root/<schema>/<table>.parquet``, in the given order."""
    counts: dict[str, int] = {}
    for table in tables:
        rows = parents_first(
            read_rows(root / str(table.schema) / f"{table.name}.parquet", table), table
        )
        for i in range(0, len(rows), BATCH):
            conn.execute(table.insert(), rows[i : i + BATCH])
        counts[f"{table.schema}/{table.name}"] = len(rows)
    return counts
