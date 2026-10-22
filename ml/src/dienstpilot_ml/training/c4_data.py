"""Per-person yearly event and opportunity counts for C4, from the synthetic tables only."""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from dienstpilot_ml.features.preference import (
    N_CELLS,
    avoid_opportunities,
    event_counts,
    wish_opportunities,
)

# The only files C4 training reads, relative to the dataset folder.
FILES = (
    "planning/assignment.parquet",
    "planning/roster_variant.parquet",
    "operations/swap_offer.parquet",
    "requests/request_window.parquet",
    "requests/window_response.parquet",
    "requests/preference.parquet",
)
WISH_K, WISH_N, AVOID_K, AVOID_N = range(4)


@dataclass(frozen=True)
class PreferenceData:
    """Counts per pseudonymous staff id and year, plus the identity of the data they came from."""

    counts: dict[str, dict[int, np.ndarray]]  # staff -> year -> (4, N_CELLS)
    windows: dict[str, dict[int, int]]  # staff -> year -> answered request windows
    manifest_sha256: str
    seed: int
    generator_version: str
    file_sha256: dict[str, str]

    def upto(self, last_year: int, first_year: int = 2021) -> dict[str, np.ndarray]:
        """Return each person's counts summed over the years first_year to last_year."""
        out: dict[str, np.ndarray] = {}
        for staff, years in self.counts.items():
            tot = np.zeros((4, N_CELLS))
            for y, c in years.items():
                if first_year <= y <= last_year:
                    tot += c
            out[staff] = tot
        return out

    def year(self, year: int) -> dict[str, np.ndarray]:
        """Return each person's counts of one year (people without any are left out)."""
        return {s: ys[year] for s, ys in self.counts.items() if year in ys}

    def answered_until(self, last_year: int) -> dict[str, int]:
        """Return the number of request windows each person answered up to ``last_year``."""
        return {
            s: sum(n for y, n in ys.items() if y <= last_year) for s, ys in self.windows.items()
        }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(root: Path, through: date) -> PreferenceData:
    """Read the tables, check their hashes against the manifest, keep events up to ``through``."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for name in FILES:
        expected = manifest["files"][name]["sha256"]
        if _sha(root / name) != expected:
            raise ValueError(f"{name} does not match manifest.json")
        hashes[name] = expected
    windows = pl.read_parquet(root / "requests/request_window.parquet").filter(
        pl.col("roster_month") <= through
    )
    month_of = dict(zip(windows["id"].to_list(), windows["roster_month"].to_list(), strict=True))
    answered = pl.read_parquet(root / "requests/window_response.parquet").filter(
        pl.col("window_id").is_in(list(month_of))
    )
    prefs = pl.read_parquet(root / "requests/preference.parquet").filter(
        pl.col("window_id").is_in(list(month_of))
    )
    published = pl.read_parquet(root / "planning/roster_variant.parquet").filter(
        pl.col("status") == "published"
    )["id"]
    assign = pl.read_parquet(root / "planning/assignment.parquet").filter(
        pl.col("variant_id").is_in(published.implode()) & (pl.col("date") <= through)
    )
    swaps = pl.read_parquet(root / "operations/swap_offer.parquet")
    shift_of = {
        a: (d, s)
        for a, d, s in zip(
            assign["id"].to_list(),
            assign["date"].to_list(),
            assign["shift_type"].to_list(),
            strict=True,
        )
    }

    months: dict[tuple[str, int], list[date]] = defaultdict(list)
    n_windows: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for w, s in zip(answered["window_id"].to_list(), answered["staff_id"].to_list(), strict=True):
        m = month_of[w]
        months[(s, m.year)].append(m)
        n_windows[s][m.year] += 1
    unavailable: dict[tuple[str, int], list[date]] = defaultdict(list)
    wishes: dict[tuple[str, int], list[tuple[date, str | None]]] = defaultdict(list)
    for s, d, k, sh in zip(
        prefs["staff_id"].to_list(),
        prefs["date"].to_list(),
        prefs["kind"].to_list(),
        prefs["shift_type"].to_list(),
        strict=True,
    ):
        if k == "unavailable":
            unavailable[(s, d.year)].append(d)
        else:
            wishes[(s, d.year)].append((d, sh))
    mine: dict[tuple[str, int], list[tuple[date, str]]] = defaultdict(list)
    for s, d, sh in zip(
        assign["staff_id"].to_list(),
        assign["date"].to_list(),
        assign["shift_type"].to_list(),
        strict=True,
    ):
        mine[(s, d.year)].append((d, sh))
    away: dict[tuple[str, int], list[tuple[date, str]]] = defaultdict(list)
    for a, s in zip(swaps["assignment_id"].to_list(), swaps["offered_by"].to_list(), strict=True):
        if a in shift_of:
            away[(s, shift_of[a][0].year)].append(shift_of[a])

    keys = set(months) | set(mine) | set(away) | set(wishes)
    counts: dict[str, dict[int, np.ndarray]] = defaultdict(dict)
    for s, y in sorted(keys):
        arr = np.zeros((4, N_CELLS))
        arr[WISH_K] = event_counts(wishes.get((s, y), []))
        arr[WISH_N] = wish_opportunities(months.get((s, y), []), unavailable.get((s, y), []))
        arr[AVOID_K] = event_counts(away.get((s, y), []))
        arr[AVOID_N] = avoid_opportunities(mine.get((s, y), []))
        counts[s][y] = arr
    return PreferenceData(
        {s: dict(v) for s, v in counts.items()},
        {s: dict(v) for s, v in n_windows.items()},
        _sha(root / "manifest.json"),
        int(manifest["seed"]),
        str(manifest["generator_version"]),
        hashes,
    )
