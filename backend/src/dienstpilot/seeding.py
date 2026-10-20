"""Load the synthetic seed (Parquet + manifest) into Postgres: python -m dienstpilot.seeding DIR.

Checks the manifest's hashes and row counts, checks references across contexts (there are no
foreign keys between schemas), then replaces the seeded tables in one transaction.
"""

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import Connection, create_engine, func, select, text

from dienstpilot.operations import seed as operations
from dienstpilot.organization import seed as organization
from dienstpilot.planning import seed as planning
from dienstpilot.requests import seed as requests
from dienstpilot.shared.settings import get_settings

CONTEXTS: list[tuple[str, Callable[[Connection, Path], dict[str, int]], list[Any]]] = [
    ("organization", organization.load, organization.TABLES),
    ("requests", requests.load, requests.TABLES),
    ("planning", planning.load, planning.TABLES),
    ("operations", operations.load, operations.TABLES),
]

# Cross-context references: (table, column) → (table, column) it must exist in.
REFERENCES: list[tuple[str, str, str, str]] = [
    ("requests/window_response", "staff_id", "organization/staff", "id"),
    ("requests/preference", "staff_id", "organization/staff", "id"),
    ("requests/preference", "shift_type", "organization/shift_type", "code"),
    ("requests/leave_request", "staff_id", "organization/staff", "id"),
    ("requests/leave_request", "decided_by", "organization/staff", "id"),
    ("planning/roster_run", "rule_set_version", "organization/rule_set", "version"),
    ("planning/assignment", "staff_id", "organization/staff", "id"),
    ("planning/assignment", "shift_type", "organization/shift_type", "code"),
    ("planning/approval", "approved_by", "organization/staff", "id"),
    ("operations/absence", "staff_id", "organization/staff", "id"),
    ("operations/swap_offer", "assignment_id", "planning/assignment", "id"),
    ("operations/swap_offer", "offered_by", "organization/staff", "id"),
    ("operations/swap_offer", "accepted_by", "organization/staff", "id"),
    ("operations/cover_cascade", "assignment_id", "planning/assignment", "id"),
    ("operations/cover_cascade", "covered_by", "organization/staff", "id"),
    ("operations/cover_offer", "staff_id", "organization/staff", "id"),
]


class SeedError(RuntimeError):
    """The seed directory is incomplete, altered or inconsistent."""


def verify(root: Path) -> dict[str, Any]:
    """Check hashes, row counts and cross-context references; return the manifest."""
    manifest: dict[str, Any] = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for rel, info in manifest["files"].items():
        data = (root / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise SeedError(f"{rel}: content does not match the manifest")
    for src, col, dst, key in REFERENCES:
        values = pl.read_parquet(root / f"{src}.parquet", columns=[col])[col].drop_nulls().unique()
        known = pl.read_parquet(root / f"{dst}.parquet", columns=[key])[key]
        unknown = values.filter(~values.is_in(known.implode()))
        if unknown.len():
            raise SeedError(f"{src}.{col}: {unknown.len()} values not in {dst}.{key}")
    return manifest


def load(root: Path, url: str | None = None) -> dict[str, int]:
    """Replace all seeded tables with the seed in ``root``; return row counts per table."""
    manifest = verify(root)
    engine = create_engine(url or get_settings().database_url)
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        names = ", ".join(
            t.fullname for _, _, tables in reversed(CONTEXTS) for t in reversed(tables)
        )
        conn.execute(text(f"TRUNCATE {names}"))
        for _, loader, _ in CONTEXTS:
            counts.update(loader(conn, root))
        for _, _, tables in CONTEXTS:
            for t in tables:
                n = conn.execute(select(func.count()).select_from(t)).scalar_one()
                expected = manifest["files"][f"{t.schema}/{t.name}.parquet"]["rows"]
                if n != expected:
                    raise SeedError(
                        f"{t.fullname}: {n} rows in the database, manifest says {expected}"
                    )
    engine.dispose()
    return counts


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0] if args else "data/synthetic/v1")
    counts = load(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    print(
        f"seed: loaded {sum(counts.values())} rows into {len(counts)} tables "
        f"(seed {manifest['seed']}, generator v{manifest['generator_version']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
