"""Load the synthetic tables C3 may use, never the ground-truth folder (ADR-007)."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from dienstpilot_ml.features.absence import SERIES_START, Calendar, DailySeries, daily_counts

# The only files training reads, relative to the dataset folder.
FILES = (
    "operations/absence.parquet",
    "organization/holiday.parquet",
    "organization/school_holiday.parquet",
    "planning/assignment.parquet",
    "planning/roster_variant.parquet",
)


@dataclass(frozen=True)
class Dataset:
    """Department-level inputs for C3 and the identity of the data they came from."""

    series: DailySeries  # absent people per day, 2021-01-01 to ``through``
    calendar: Calendar
    night_shifts: dict[date, int]
    manifest_sha256: str
    seed: int
    generator_version: str
    file_sha256: dict[str, str]  # the files read, as recorded in the manifest and re-checked


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(root: Path, through: date) -> Dataset:
    """Read the tables from ``root`` and check their hashes against its manifest."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for name in FILES:
        expected = manifest["files"][name]["sha256"]
        if _sha(root / name) != expected:
            raise ValueError(f"{name} does not match manifest.json")
        hashes[name] = expected
    absence = pl.read_parquet(root / "operations/absence.parquet").filter(
        pl.col("category") == "sick"
    )
    intervals = list(
        zip(absence["start_date"].to_list(), absence["end_date"].to_list(), strict=True)
    )
    holidays = frozenset(pl.read_parquet(root / "organization/holiday.parquet")["date"].to_list())
    school: set[date] = set()
    for a, b in (
        pl.read_parquet(root / "organization/school_holiday.parquet")
        .select("start_date", "end_date")
        .iter_rows()
    ):
        school.update(a + timedelta(days=i) for i in range((b - a).days + 1))
    published = pl.read_parquet(root / "planning/roster_variant.parquet").filter(
        pl.col("status") == "published"
    )["id"]
    nights = (
        pl.read_parquet(root / "planning/assignment.parquet")
        .filter(pl.col("variant_id").is_in(published.implode()) & (pl.col("shift_type") == "nacht"))
        .group_by("date")
        .len()
    )
    return Dataset(
        series=daily_counts(intervals, SERIES_START, through),
        calendar=Calendar(holidays, frozenset(school)),
        night_shifts=dict(zip(nights["date"].to_list(), nights["len"].to_list(), strict=True)),
        manifest_sha256=_sha(root / "manifest.json"),
        seed=int(manifest["seed"]),
        generator_version=str(manifest["generator_version"]),
        file_sha256=hashes,
    )
