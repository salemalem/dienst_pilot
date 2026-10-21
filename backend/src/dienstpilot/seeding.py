"""Load the synthetic seed (Parquet + manifest) into Postgres: python -m dienstpilot.seeding DIR.

Checks the manifest's hashes and row counts, checks references across contexts (there are no
foreign keys between schemas), then replaces the seeded tables in one transaction.
"""

import hashlib
import json
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import Connection, create_engine, func, select, text

from dienstpilot.audit import seed as audit
from dienstpilot.identity import seed as identity
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
        all_tables = (
            [t for _, _, tables in CONTEXTS for t in tables] + identity.TABLES + audit.TABLES
        )
        names = ", ".join(t.fullname for t in reversed(all_tables))
        conn.execute(text(f"TRUNCATE {names}"))
        for _, loader, _ in CONTEXTS:
            counts.update(loader(conn, root))
        department_id, staff_by_name, names_by_id = _department(root)
        counts["identity/user"] = identity.load_personas(conn, department_id, staff_by_name)
        counts["audit/event"] = audit.load_events(
            conn, history_events(root, department_id, names_by_id)
        )
        for _, _, tables in CONTEXTS:
            for t in tables:
                key = f"{t.schema}/{t.name}.parquet"
                if key not in manifest["files"]:
                    continue
                n = conn.execute(select(func.count()).select_from(t)).scalar_one()
                expected = manifest["files"][key]["rows"]
                if n != expected:
                    raise SeedError(
                        f"{t.fullname}: {n} rows in the database, manifest says {expected}"
                    )
    engine.dispose()
    return counts


def _department(root: Path) -> tuple[str, dict[str, str], dict[str, str]]:
    deps = pl.read_parquet(root / "organization" / "department.parquet")
    if deps.height != 1:
        raise SeedError("the seed must contain exactly one department")
    staff = pl.read_parquet(root / "organization" / "staff.parquet")
    by_name = dict(zip(staff["display_name"].to_list(), staff["id"].to_list(), strict=True))
    by_id = {v: k for k, v in by_name.items()}
    return str(deps["id"][0]), by_name, by_id


def _event(
    at: Any,
    department_id: str,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str | None,
    staff_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    key = f"{action}/{subject_id}/{staff_id}/{at.isoformat()}"
    return {
        "id": uuid.uuid5(uuid.NAMESPACE_URL, f"dienstpilot/audit/{key}"),
        "occurred_at": at,
        "department_id": uuid.UUID(department_id),
        "actor_user_id": None,
        "actor_label": actor,
        "action": action,
        "subject_type": subject_type,
        "subject_id": None if subject_id is None else uuid.UUID(subject_id),
        "staff_id": None if staff_id is None else uuid.UUID(staff_id),
        "payload": payload,
    }


def history_events(root: Path, department_id: str, names: dict[str, str]) -> list[dict[str, Any]]:
    """Derive audit events from the seeded history (decisions, requests, sick reports, cover)."""

    def t(name: str) -> pl.DataFrame:
        return pl.read_parquet(root / f"{name}.parquet")

    def who(staff_id: str | None) -> str:
        return names.get(staff_id or "", "System")

    ev: list[dict[str, Any]] = []
    runs = t("planning/roster_run")
    variants = t("planning/roster_variant").join(
        runs.select(pl.col("id").alias("run_id"), "roster_month", "rule_set_version"), on="run_id"
    )
    for r in (
        t("planning/approval")
        .join(
            variants.select(pl.col("id").alias("variant_id"), "roster_month", "rule_set_version"),
            on="variant_id",
        )
        .iter_rows(named=True)
    ):
        ev.append(
            _event(
                r["approved_at"],
                department_id,
                who(r["approved_by"]),
                "roster.published",
                "roster_variant",
                r["variant_id"],
                None,
                {
                    "roster_month": r["roster_month"].isoformat(),
                    "rule_set_version": r["rule_set_version"],
                },
            )
        )
    for r in t("requests/leave_request").iter_rows(named=True):
        dates = {"start_date": r["start_date"].isoformat(), "end_date": r["end_date"].isoformat()}
        ev.append(
            _event(
                r["submitted_at"],
                department_id,
                who(r["staff_id"]),
                "leave.requested",
                "leave_request",
                r["id"],
                r["staff_id"],
                dates,
            )
        )
        if r["decided_at"] is not None:
            ev.append(
                _event(
                    r["decided_at"],
                    department_id,
                    who(r["decided_by"]),
                    f"leave.{r['status']}",
                    "leave_request",
                    r["id"],
                    r["staff_id"],
                    {**dates, "decision_reason": r["decision_reason"]},
                )
            )
    window_months = dict(
        zip(
            t("requests/request_window")["id"].to_list(),
            t("requests/request_window")["roster_month"].to_list(),
            strict=True,
        )
    )
    for r in t("requests/window_response").iter_rows(named=True):
        ev.append(
            _event(
                r["submitted_at"],
                department_id,
                who(r["staff_id"]),
                "preferences.submitted",
                "request_window",
                r["window_id"],
                r["staff_id"],
                {"roster_month": window_months[r["window_id"]].isoformat()},
            )
        )
    for r in t("operations/swap_offer").iter_rows(named=True):
        ev.append(
            _event(
                r["offered_at"],
                department_id,
                who(r["offered_by"]),
                "swap.offered",
                "swap_offer",
                r["id"],
                r["offered_by"],
                {},
            )
        )
        if r["accepted_at"] is not None:
            ev.append(
                _event(
                    r["accepted_at"],
                    department_id,
                    who(r["accepted_by"]),
                    "swap.accepted",
                    "swap_offer",
                    r["id"],
                    r["accepted_by"],
                    {"approval": r["approval"]},
                )
            )
    for r in t("operations/absence").iter_rows(named=True):
        ev.append(
            _event(
                r["reported_at"],
                department_id,
                who(r["staff_id"]),
                "absence.reported",
                "absence",
                r["id"],
                r["staff_id"],
                {
                    "start_date": r["start_date"].isoformat(),
                    "end_date": r["end_date"].isoformat(),
                    "category": r["category"],
                },
            )
        )
    for r in t("operations/cover_cascade").iter_rows(named=True):
        ev.append(
            _event(
                r["closed_at"],
                department_id,
                "System",
                "cover.decided",
                "cover_cascade",
                r["id"],
                r["covered_by"],
                {"outcome": r["outcome"]},
            )
        )
    return ev


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
