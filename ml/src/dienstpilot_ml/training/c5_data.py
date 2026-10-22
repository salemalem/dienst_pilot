"""One row per cover offer for C5, from the synthetic tables only (never the ground truth).

The features are computed as of the moment of each offer: the roster as worked (published, with
swaps and the earlier cover searches applied in time order), so nothing after the offer is read.
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from dienstpilot_ml.features.cover import (
    WORKING,
    CoverFeatures,
    confirmed_pref,
    credited_hours,
    days_since,
    matrix,
    month_contract_hours,
    notice_hours,
    request_hour,
)

# The only files C5 training reads, relative to the dataset folder.
FILES = (
    "planning/assignment.parquet",
    "planning/roster_variant.parquet",
    "organization/shift_type.parquet",
    "organization/contract.parquet",
    "operations/cover_offer.parquet",
    "operations/cover_cascade.parquet",
    "operations/swap_offer.parquet",
    "requests/preference.parquet",
)


@dataclass(frozen=True)
class OfferTable:
    """Every cover offer up to ``through`` with its features and label, in time order."""

    x: np.ndarray  # (n, len(FEATURES))
    y: np.ndarray  # 1 accepted, 0 otherwise
    year: np.ndarray  # year of the offer
    cascade: list[str]  # cascade id per offer (the bootstrap resamples cascades)
    manifest_sha256: str
    seed: int
    generator_version: str
    file_sha256: dict[str, str]

    def take(self, mask: np.ndarray) -> "OfferTable":
        """Return the rows where ``mask`` is true."""
        idx = np.flatnonzero(mask)
        return OfferTable(
            self.x[idx],
            self.y[idx],
            self.year[idx],
            [self.cascade[i] for i in idx],
            self.manifest_sha256,
            self.seed,
            self.generator_version,
            self.file_sha256,
        )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=None)


def load(root: Path, through: date) -> OfferTable:
    """Read the tables, check their hashes against the manifest, keep offers up to ``through``."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    hashes: dict[str, str] = {}
    for name in FILES:
        expected = manifest["files"][name]["sha256"]
        if _sha(root / name) != expected:
            raise ValueError(f"{name} does not match manifest.json")
        hashes[name] = expected
    end = datetime.combine(through + timedelta(days=1), time(0, 0))

    shifts = pl.read_parquet(root / "organization/shift_type.parquet")
    start_of = dict(zip(shifts["code"].to_list(), shifts["start_time"].to_list(), strict=True))
    published = pl.read_parquet(root / "planning/roster_variant.parquet").filter(
        pl.col("status") == "published"
    )["id"]
    assign = pl.read_parquet(root / "planning/assignment.parquet").filter(
        pl.col("variant_id").is_in(published.implode())
    )
    what: dict[str, tuple[date, str]] = {}  # assignment id -> (day, shift type)
    holder: dict[str, str | None] = {}
    hours: dict[tuple[str, date], float] = defaultdict(float)  # (staff, month) -> credited hours
    days: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))  # staff -> day -> n

    def give(aid: str, staff: str | None, sign: int) -> None:
        if staff is None:
            return
        d, sh = what[aid]
        hours[(staff, d.replace(day=1))] += sign * credited_hours(sh)
        if sh in WORKING:
            days[staff][d] += sign

    for aid, s, d, sh in zip(
        assign["id"].to_list(),
        assign["staff_id"].to_list(),
        assign["date"].to_list(),
        assign["shift_type"].to_list(),
        strict=True,
    ):
        what[aid] = (d, sh)
        holder[aid] = s
        give(aid, s, +1)

    contracts: dict[str, list[tuple[float, date, date | None]]] = defaultdict(list)
    for s, wh, a, b in (
        pl.read_parquet(root / "organization/contract.parquet")
        .select("staff_id", "weekly_hours", "valid_from", "valid_to")
        .iter_rows()
    ):
        contracts[s].append((float(wh), a, b))

    def weekly(staff: str, day: date) -> float:
        for wh, a, b in contracts[staff]:
            if a <= day and (b is None or day <= b):
                return wh
        return 40.0

    prefs = pl.read_parquet(root / "requests/preference.parquet").filter(
        (pl.col("kind") != "unavailable") & pl.col("shift_type").is_not_null()
    )
    wishes: dict[str, list[tuple[date, str | None]]] = defaultdict(list)
    avoids: dict[str, list[tuple[date, str | None]]] = defaultdict(list)
    for s, d, k, sh in zip(
        prefs["staff_id"].to_list(),
        prefs["date"].to_list(),
        prefs["kind"].to_list(),
        prefs["shift_type"].to_list(),
        strict=True,
    ):
        (avoids if k == "avoid_shift" else wishes)[s].append((d, sh))

    cascades = pl.read_parquet(root / "operations/cover_cascade.parquet")
    cascade_shift = dict(
        zip(cascades["id"].to_list(), cascades["assignment_id"].to_list(), strict=True)
    )
    offers = pl.read_parquet(root / "operations/cover_offer.parquet").filter(
        pl.col("asked_at").dt.replace_time_zone(None) < end
    )
    swaps = pl.read_parquet(root / "operations/swap_offer.parquet").filter(
        pl.col("status") == "accepted"
    )

    # Events in time order: (time, order, kind, payload); at equal times changes come before offers.
    events: list[tuple[datetime, int, str, tuple[Any, ...]]] = []
    for a, at, to in zip(
        swaps["assignment_id"].to_list(),
        swaps["accepted_at"].to_list(),
        swaps["accepted_by"].to_list(),
        strict=True,
    ):
        if a in what:
            events.append((_utc(at), 0, "set", (a, to)))
    for a, o, c, by in zip(
        cascades["assignment_id"].to_list(),
        cascades["opened_at"].to_list(),
        cascades["closed_at"].to_list(),
        cascades["covered_by"].to_list(),
        strict=True,
    ):
        if a not in what:
            continue
        events.append((_utc(o), 0, "set", (a, None)))
        if by is not None:
            events.append((_utc(c), 1, "cover", (a, by)))
    for r in offers.iter_rows(named=True):
        events.append((_utc(r["asked_at"]), 2, "offer", (r,)))
    events.sort(key=lambda e: (e[0], e[1]))

    last_cover: dict[str, datetime] = {}
    rows: list[CoverFeatures] = []
    labels: list[float] = []
    years: list[int] = []
    cids: list[str] = []
    for at, _, kind, payload in events:
        if kind == "set" or kind == "cover":
            aid, to = payload
            give(aid, holder[aid], -1)
            holder[aid] = to
            give(aid, to, +1)
            if kind == "cover":
                last_cover[to] = at
            continue
        r = payload[0]
        day, sh = what[cascade_shift[r["cascade_id"]]]
        p = r["staff_id"]
        month = day.replace(day=1)
        target = month_contract_hours(weekly(p, day), month)
        n7 = sum(days[p].get(day - timedelta(days=i), 0) for i in range(1, 8))
        start = (
            datetime.combine(day, start_of[sh]) if start_of[sh] else datetime.combine(day, time(0))
        )
        rows.append(
            CoverFeatures(
                hours_ratio=hours[(p, month)] / target if target else 0.0,
                days_since_last_cover=days_since(last_cover.get(p), at),
                shifts_last_7d=float(n7),
                notice_hours=notice_hours(at, start),
                shift_type=sh,
                weekday=day.weekday(),
                request_hour=request_hour(at),
                confirmed_pref=confirmed_pref(wishes[p], avoids[p], at.date(), sh),
            )
        )
        labels.append(1.0 if r["response"] == "accepted" else 0.0)
        years.append(at.year)
        cids.append(r["cascade_id"])
    return OfferTable(
        matrix(rows),
        np.array(labels),
        np.array(years),
        cids,
        _sha(root / "manifest.json"),
        int(manifest["seed"]),
        str(manifest["generator_version"]),
        hashes,
    )
