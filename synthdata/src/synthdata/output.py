"""Write the dataset as Parquet (one file per table) plus manifest.json.

Every column has an explicit type, rows are sorted, and nothing depends on wall-clock time, so
the same seed produces byte-identical files.
"""

import hashlib
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import polars as pl

from synthdata import GENERATOR_VERSION
from synthdata.config import DEMO_END, DEMO_NOW, DEMO_START, HISTORY_END, HISTORY_START, PARAMS
from synthdata.generate import Dataset
from synthdata.rules import RULE_SETS

S, D, T, B, F, N = pl.String, pl.Date, pl.Time, pl.Boolean, pl.Float64, pl.Int32
TS = pl.Datetime("us", "UTC")

SCHEMAS: dict[str, dict[str, Any]] = {
    "organization/department": {"id": S, "name": S, "short_name": S},
    "organization/staff": {"id": S, "department_id": S, "display_name": S},
    "organization/contract": {
        "id": S,
        "staff_id": S,
        "role": S,
        "title_de": S,
        "title_en": S,
        "weekly_hours": F,
        "valid_from": D,
        "valid_to": D,
    },
    "organization/qualification": {"code": S, "name_de": S, "name_en": S},
    "organization/staff_qualification": {
        "staff_id": S,
        "qualification": S,
        "valid_from": D,
        "valid_to": D,
    },
    "organization/staff_rotation": {
        "id": S,
        "staff_id": S,
        "target": S,
        "start_date": D,
        "end_date": D,
    },
    "organization/shift_type": {
        "code": S,
        "letter_de": S,
        "letter_en": S,
        "name_de": S,
        "name_en": S,
        "start_time": T,
        "end_time": T,
        "ends_next_day": B,
        "break_minutes": N,
        "net_hours": F,
        "kind": S,
        "counts_as_working_time": B,
        "burden_weight": F,
    },
    "organization/shift_demand": {
        "date": D,
        "shift_type": S,
        "qualification": S,
        "required_count": N,
    },
    "organization/holiday": {"date": D, "name_de": S, "name_en": S},
    "organization/school_holiday": {
        "id": S,
        "start_date": D,
        "end_date": D,
        "name_de": S,
        "name_en": S,
    },
    "organization/rule_set": {
        "id": S,
        "version": S,
        "effective_from": D,
        "rules": S,
        "change_note_de": S,
        "change_note_en": S,
    },
    "requests/request_window": {
        "id": S,
        "roster_month": D,
        "opens_at": TS,
        "closes_at": TS,
        "status": S,
        "recipient_count": N,
    },
    "requests/window_response": {"window_id": S, "staff_id": S, "submitted_at": TS},
    "requests/preference": {
        "id": S,
        "window_id": S,
        "staff_id": S,
        "date": D,
        "kind": S,
        "shift_type": S,
        "important": B,
    },
    "requests/leave_request": {
        "id": S,
        "staff_id": S,
        "start_date": D,
        "end_date": D,
        "submitted_at": TS,
        "status": S,
        "decided_at": TS,
        "decided_by": S,
        "decision_reason_code": S,
        "decision_reason": S,
    },
    "planning/roster_run": {
        "id": S,
        "roster_month": D,
        "rule_set_version": S,
        "planner_kind": S,
        "generator_version": S,
        "created_at": TS,
    },
    "planning/roster_variant": {"id": S, "run_id": S, "label": S, "status": S, "published_at": TS},
    "planning/approval": {"id": S, "variant_id": S, "approved_by": S, "approved_at": TS, "kind": S},
    "planning/assignment": {"id": S, "variant_id": S, "staff_id": S, "date": D, "shift_type": S},
    "operations/absence": {
        "id": S,
        "staff_id": S,
        "start_date": D,
        "end_date": D,
        "category": S,
        "reported_at": TS,
    },
    "operations/swap_offer": {
        "id": S,
        "assignment_id": S,
        "offered_by": S,
        "offered_at": TS,
        "accepted_by": S,
        "accepted_at": TS,
        "status": S,
        "approval": S,
    },
    "operations/cover_cascade": {
        "id": S,
        "assignment_id": S,
        "absence_id": S,
        "opened_at": TS,
        "closed_at": TS,
        "outcome": S,
        "covered_by": S,
    },
    "operations/cover_offer": {
        "id": S,
        "cascade_id": S,
        "staff_id": S,
        "rank": N,
        "asked_at": TS,
        "responded_at": TS,
        "response": S,
    },
}
TRUTH_SCHEMAS: dict[str, dict[str, Any]] = {
    "sickness_wave": {
        "season_start_year": N,
        "peak_offset_days": F,
        "width_days": F,
        "amplitude": F,
        "autumn_bump": F,
    },
    "department_sickness_hazard": {"date": D, "expected_new_episodes": F, "seasonal_factor": F},
    "published_violations": {"roster_month": D, "date": D, "staff_id": S, "rule": S, "detail": S},
    "in_month_breaches": {
        "date": D,
        "staff_id": S,
        "rule": S,
        "detail": S,
        "source": S,
        "source_id": S,
    },
}


def _cell(v: object) -> object:
    if isinstance(v, datetime):
        return v.astimezone(UTC)
    if isinstance(v, (date, time, int, float, bool, str)) or v is None:
        return v
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return str(v)


def _frame(rows: list[dict[str, object]], schema: dict[str, Any]) -> pl.DataFrame:
    data = {c: [_cell(r.get(c)) for r in rows] for c in schema}
    df = pl.DataFrame(data, schema=schema, strict=False)
    return df.sort(list(schema))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_dataset(ds: Dataset, seed: int, out: Path) -> dict[str, Any]:
    """Write all tables and the manifest; return the manifest."""
    files: dict[str, dict[str, Any]] = {}
    for name, schema in SCHEMAS.items():
        files[f"{name}.parquet"] = _write(
            out, f"{name}.parquet", _frame(ds.tables.get(name, []), schema)
        )
    truth_files: dict[str, dict[str, Any]] = {}
    for name, rows in ds.truth.items():
        schema = TRUTH_SCHEMAS.get(name) or {k: (S if k == "staff_id" else F) for k in rows[0]}
        truth_files[f"_truth/{name}.parquet"] = _write(
            out, f"_truth/{name}.parquet", _frame(rows, schema)
        )
    params = {k: getattr(PARAMS, k) for k in PARAMS.__dataclass_fields__}
    (out / "_truth").mkdir(parents=True, exist_ok=True)
    (out / "_truth" / "params.json").write_text(
        json.dumps(params, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest: dict[str, Any] = {
        "dataset": "dienstpilot-synthetic",
        "description": (
            "Synthetic data for the fictional Klinik für Innere Medizin, Klinikum Musterstadt."
        ),
        "seed": seed,
        "generator_version": GENERATOR_VERSION,
        "periods": {
            "history": {
                "start": HISTORY_START.isoformat(),
                "end": HISTORY_END.isoformat(),
                "use": "training and evaluation",
            },
            "demo": {
                "start": DEMO_START.isoformat(),
                "end": DEMO_END.isoformat(),
                "use": "demo period: live and published months for the UI; not for model training",
                "now": DEMO_NOW.isoformat(),
            },
        },
        "rule_sets": [
            {"version": r.version, "effective_from": r.effective_from.isoformat()}
            for r in RULE_SETS
        ],
        "files": files,
        "truth_files": truth_files,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _write(out: Path, rel: str, df: pl.DataFrame) -> dict[str, Any]:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path, compression="zstd", statistics=True)
    return {"rows": df.height, "sha256": _sha256(path)}
