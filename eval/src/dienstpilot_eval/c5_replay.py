"""Replay of the 2025 sick calls under different cover-ordering policies (C5, PROMOTION_RULE.md).

A simulation against the generator's behaviour model: it reads the ground truth (the latent
cover willingness), which only ``eval/`` may do (ASSUMPTIONS §14). Nothing here says anything
about real people.

The candidate pool is the product's: the quick filter of ``backend/.../app/cover.py`` and then
the validator (C2) ``validate_change``. Acceptance is drawn from the generator's latent model with
common random numbers across policies.
"""

import hashlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from dienstpilot_validator import Assignment, MonthInput, validate_change

from dienstpilot_eval.inputs import Data, month_end
from dienstpilot_ml.cover_ranker.models import Bundle
from dienstpilot_ml.cover_ranker.policy import Ranked
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

ROLE_SHIFTS = {
    "chefaerztin": {"ruf"},
    "oberarzt": {"frueh", "ruf"},
    "facharzt": {"frueh", "spaet", "nacht", "bereitschaft"},
    "assistenzarzt": {"frueh", "spaet", "nacht", "bereitschaft"},
}
COVER_ROLES = ("assistenzarzt", "facharzt", "oberarzt")
MAX_ASKS = 6
WINDOW_MIN = 15
PREF_SHIFTS = ("frueh", "spaet", "nacht", "bereitschaft")
DAYS = ("mo", "di", "mi", "do", "fr", "sa", "so")


def _naive(t: datetime) -> datetime:
    return t.replace(tzinfo=None)


def _unit(*key: object) -> float:
    """Return a deterministic uniform number in [0, 1) for a key (common random numbers)."""
    h = hashlib.sha256("|".join(map(str, key)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def gini(values: list[float]) -> float:
    """Return the Gini coefficient of non-negative values (0 when all are equal or zero)."""
    v = np.sort(np.asarray(values, dtype=float))
    if v.sum() == 0:
        return 0.0
    n = len(v)
    return float((2 * np.sum((np.arange(1, n + 1)) * v) / (n * v.sum())) - (n + 1) / n)


@dataclass
class Latent:
    """The generator's cover behaviour of one person (from the ground truth)."""

    willingness: float
    decay: float
    affinity: np.ndarray  # (7, 4) weekday x shift, incl. night/weekend

    def liking(self, day: date, shift: str) -> float:
        """Return the latent liking of a shift on a day (0 for shifts the generator ignores)."""
        if shift not in PREF_SHIFTS:
            return 0.0
        return float(self.affinity[day.weekday(), PREF_SHIFTS.index(shift)])


def load_latents(root: Path) -> dict[str, Latent]:
    """Read the latent cover parameters and the shift affinity of every person."""
    out: dict[str, Latent] = {}
    for r in pl.read_parquet(root / "_truth" / "staff_latent.parquet").iter_rows(named=True):
        aff = np.zeros((7, 4))
        for wd in range(7):
            for si, sh in enumerate(PREF_SHIFTS):
                v = float(r[f"pref_{DAYS[wd]}_{sh}"])
                if sh in ("nacht", "bereitschaft"):
                    v += float(r["night_tolerance"])
                if wd >= 5:
                    v -= float(r["weekend_aversion"])
                aff[wd, si] = v
        out[r["staff_id"]] = Latent(
            float(r["cover_willingness"]), float(r["cover_load_decay"]), aff
        )
    return out


def p_accept_true(lat: Latent, day: date, shift: str, recent_covers: int) -> float:
    """Return the generator's acceptance probability."""
    z = lat.willingness + 0.4 * lat.liking(day, shift) - lat.decay * recent_covers
    return float(1.0 / (1.0 + np.exp(-z)))


@dataclass
class Metrics:
    """What one replay run measured."""

    cascades: int = 0
    filled: int = 0
    escalated: int = 0
    asks: int = 0
    asks_filled: int = 0
    minutes_filled: list[float] = field(default_factory=list)
    covers: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class World:
    """The data a replay needs, loaded once and shared by every policy and replicate."""

    def __init__(self, root: Path) -> None:
        """Load the dataset (as ``Data``), the ground truth and the history before 2025."""
        self.root = root
        self.data = Data(root)
        self.latents = load_latents(root)
        d = self.data
        self.types = d.shift_types
        cascades = pl.read_parquet(root / "operations/cover_cascade.parquet")
        offers = pl.read_parquet(root / "operations/cover_offer.parquet")
        self.assign = d.assignment  # id -> (staff, day, shift, roster month)
        # Covers before 2025: (person, shift day, time the search closed).
        self.covers_before: list[tuple[str, date, datetime]] = []
        for a, by, closed in zip(
            cascades["assignment_id"].to_list(),
            cascades["covered_by"].to_list(),
            cascades["closed_at"].to_list(),
            strict=True,
        ):
            if by is not None and a in self.assign and _naive(closed).year < 2025:
                self.covers_before.append((by, self.assign[a][1], _naive(closed)))
        # Reliability for policy (c): smoothed acceptance rate over the 2021-2024 offers.
        past = offers.filter(pl.col("asked_at").dt.year() < 2025)
        asked: dict[str, int] = defaultdict(int)
        accepted: dict[str, int] = defaultdict(int)
        for s, r in zip(past["staff_id"].to_list(), past["response"].to_list(), strict=True):
            asked[s] += 1
            accepted[s] += r == "accepted"
        self.reliability = {s: (accepted[s] + 1) / (asked[s] + 2) for s in asked}
        prefs = d.prefs.filter(
            (pl.col("kind") != "unavailable") & pl.col("shift_type").is_not_null()
        )
        self.wishes: dict[str, list[tuple[date, str | None]]] = defaultdict(list)
        self.avoids: dict[str, list[tuple[date, str | None]]] = defaultdict(list)
        for s, day, k, sh in zip(
            prefs["staff_id"].to_list(),
            prefs["date"].to_list(),
            prefs["kind"].to_list(),
            prefs["shift_type"].to_list(),
            strict=True,
        ):
            (self.avoids if k == "avoid_shift" else self.wishes)[s].append((day, sh))
        swaps = pl.read_parquet(root / "operations/swap_offer.parquet").filter(
            pl.col("status") == "accepted"
        )
        self.swaps = sorted(
            zip(
                swaps["accepted_at"].to_list(),
                swaps["assignment_id"].to_list(),
                swaps["accepted_by"].to_list(),
                strict=True,
            ),
            key=lambda x: x[0],
        )
        self.absences = sorted(
            (a for a in d.absences if _naive(a[3]).year == 2025), key=lambda a: a[3]
        )
        self.population = [
            s
            for s, p in d.people.items()
            if any(
                c[0] in COVER_ROLES
                and c[2] <= date(2025, 12, 31)
                and (c[3] is None or c[3] >= date(2025, 1, 1))
                for c in p.contracts
            )
        ]
        self.months = [date(2025, m, 1) for m in range(1, 13)]
        self.base = {m: d.month(m) for m in (date(2024, 12, 1), *self.months, date(2026, 1, 1))}
        self.facts = {m: replace(md.month, assignments=()) for m, md in self.base.items()}
        self.unavailable: dict[date, dict[str, set[date]]] = defaultdict(lambda: defaultdict(set))
        for r in d.prefs.filter(pl.col("kind") == "unavailable").iter_rows(named=True):
            self.unavailable[r["roster_month"]][r["staff_id"]].add(r["date"])


class State:
    """The roster as a policy has made it, plus who took which cover."""

    def __init__(self, w: World) -> None:
        """Start from the published 2025 roster with the swaps of the data applied."""
        self.w = w
        self.holder: dict[str, str | None] = {
            aid: v[0] for aid, v in w.assign.items() if v[3] >= date(2024, 12, 1)
        }
        for _, aid, to in w.swaps:
            if aid in self.holder and w.assign[aid][1].year == 2025:
                self.holder[aid] = to
        self.by_day: dict[date, list[str]] = defaultdict(list)
        for aid in self.holder:
            self.by_day[w.assign[aid][1]].append(aid)
        self.cover_times: dict[str, list[datetime]] = defaultdict(list)
        self.cover_days: dict[str, list[date]] = defaultdict(list)
        for p, day, t in w.covers_before:
            self.cover_times[p].append(t)
            self.cover_days[p].append(day)

    def shifts_on(self, day: date) -> list[tuple[str, str | None, str]]:
        """Return (assignment id, holder, shift type) of every shift on a day."""
        return [(a, self.holder[a], self.w.assign[a][2]) for a in self.by_day.get(day, [])]

    def month_assignments(self, m: date) -> tuple[Assignment, ...]:
        """Return the month and the seven days before it as the policy's roster holds them."""
        if m == date(2025, 1, 1):
            hist = self.w.base[m].history
        else:
            hist = tuple(
                Assignment(h, self.w.assign[a][1], self.w.assign[a][2])
                for d in (m - timedelta(days=i) for i in range(7, 0, -1))
                for a, h, _ in self.shifts_on(d)
                if h
            )
        cur = tuple(
            Assignment(h, self.w.assign[a][1], self.w.assign[a][2])
            for a, h in self.holder.items()
            if h and self.w.assign[a][3] == m
        )
        return hist + cur

    def covers_last_90(self, p: str, now: datetime) -> int:
        """Return the covers the person took in the 90 days before ``now``."""
        since = now - timedelta(days=90)
        return sum(1 for t in self.cover_times[p] if since <= t <= now)

    def last_cover(self, p: str, now: datetime) -> datetime | None:
        """Return the time of the person's latest cover before ``now``."""
        past = [t for t in self.cover_times[p] if t <= now]
        return max(past) if past else None

    def recent_30(self, p: str, day: date) -> int:
        """Return the covers the person took for shifts 0 to 30 days before ``day``."""
        return sum(1 for x in self.cover_days[p] if 0 <= (day - x).days <= 30)


Orderer = Callable[[list[Ranked]], list[Ranked]]


def _needs(w: World, holder: str | None, day: date, shift: str) -> set[str]:
    if shift == "ruf":
        return {"oberarzt"}
    if shift in ("nacht", "bereitschaft"):
        needs = {"nachtdienstfaehig"}
        if shift == "bereitschaft" and holder and w.data.people[holder].has("facharzt", day):
            needs.add("facharzt")
        return needs
    return set()


def _absent(w: World, day: date, now: datetime) -> set[str]:
    """Return who is absent on ``day``: sick reports up to the end of ``now``'s calendar day."""
    return {s for s, a, b, rep in w.absences if a <= day <= b and _naive(rep).date() <= now.date()}


def quick_filter(w: World, st: State, aid: str, now: datetime) -> list[str]:
    """Mirror ``cover.basic_candidates``: role, qualification, free that day, not absent or on leave."""
    day, shift = w.assign[aid][1], w.assign[aid][2]
    sick = st.holder[aid]
    needs = _needs(w, sick, day, shift)
    same = st.shifts_on(day)
    busy = {h for _, h, s in same if h and s in WORKING}
    on_ruf = {h for _, h, s in same if h and s == "ruf"}
    absent = _absent(w, day, now)
    out = []
    for pid, p in w.data.people.items():
        c = p.contract_on(day)
        if c is None or p.rotating(day):
            continue
        role = c[0]
        if pid == sick or shift not in ROLE_SHIFTS[role]:
            continue
        if not all(p.has(q, day) for q in needs):
            continue
        if pid in busy or pid in absent or day in w.data.leave.get(pid, set()):
            continue
        if shift == "ruf" and pid in on_ruf:
            continue
        if shift not in ("frueh", "ruf") and pid in on_ruf:
            continue
        out.append(pid)
    return out


def c2_pool(w: World, st: State, aid: str, now: datetime, people: list[str]) -> list[str]:
    """Return the colleagues who could take the shift without breaking a rule (the validator)."""
    day, shift = w.assign[aid][1], w.assign[aid][2]
    sick = st.holder[aid]
    months = {day.replace(day=1)}
    if day > month_end(day.replace(day=1)) - timedelta(days=7):
        months.add(month_end(day.replace(day=1)) + timedelta(days=1))
    inputs: dict[date, MonthInput] = {}
    months = {m for m in months if m in w.facts}
    for m in sorted(months):
        blocked: dict[str, set[date]] = {s: set(v) for s, v in w.unavailable.get(m, {}).items()}
        for s, a, b, rep in w.absences:
            if _naive(rep) <= now and b >= m and a <= month_end(m):
                lo, hi = max(a, m - timedelta(days=7)), min(b, month_end(m))
                blocked.setdefault(s, set()).update(
                    lo + timedelta(days=i) for i in range((hi - lo).days + 1)
                )
        inputs[m] = replace(
            w.facts[m],
            assignments=st.month_assignments(m),
            blocked={s: frozenset(v) for s, v in blocked.items()},
        )
    remove = [Assignment(sick, day, shift)] if sick else []
    ok = []
    for p in people:
        bad = False
        for m in sorted(months):
            _, introduced = validate_change(inputs[m], remove, [Assignment(p, day, shift)])
            if any(v.staff_id is None or v.staff_id == p for v in introduced):
                bad = True
                break
        if not bad:
            ok.append(p)
    return ok


def features(w: World, st: State, p: str, aid: str, now: datetime) -> CoverFeatures:
    """Return the C5 features of a candidate for a shift at ``now`` (same definitions as training)."""
    day, shift = w.assign[aid][1], w.assign[aid][2]
    month = day.replace(day=1)
    hours = sum(
        credited_hours(w.assign[a][2])
        for a, h in st.holder.items()
        if h == p and w.assign[a][3] == month
    )
    c = w.data.people[p].contract_on(day)
    target = month_contract_hours(c[1] if c else 40.0, month)
    n7 = sum(
        1
        for i in range(1, 8)
        for _, h, s in st.shifts_on(day - timedelta(days=i))
        if h == p and s in WORKING
    )
    st_time = w.types[shift].start if shift in w.types else None
    start = datetime.combine(day, st_time or time(0))
    return CoverFeatures(
        hours_ratio=hours / target if target else 0.0,
        days_since_last_cover=days_since(st.last_cover(p, now), now),
        shifts_last_7d=float(n7),
        notice_hours=notice_hours(now, start),
        shift_type=shift,
        weekday=day.weekday(),
        request_hour=request_hour(now),
        confirmed_pref=confirmed_pref(w.wishes[p], w.avoids[p], now.date(), shift),
    )


def run(w: World, order: Orderer, champion: Bundle, replicate: int, policy_name: str) -> Metrics:
    """Replay the 2025 sick calls once under one ordering policy."""
    st = State(w)
    m = Metrics()
    for staff, a, b, rep in w.absences:
        now = _naive(rep)
        mine = sorted(
            (w.assign[aid][1], aid)
            for aid, h in st.holder.items()
            if h == staff and a <= w.assign[aid][1] <= b
        )
        for day, aid in mine:
            shift = w.assign[aid][2]
            if shift not in ROLE_SHIFTS.get("facharzt", set()) | {"ruf"}:
                continue
            start = (
                datetime.combine(day, w.types[shift].start or time(0)) if shift in w.types else None
            )
            if start is not None and start <= now:
                continue  # already started: the Planner handles it directly
            m.cascades += 1
            people = c2_pool(w, st, aid, now, quick_filter(w, st, aid, now))
            feats = [features(w, st, p, aid, now) for p in people]
            probs = champion.predict(matrix(feats)) if people else np.array([])
            ranked = [
                Ranked(p, st.covers_last_90(p, now), f.hours_ratio, float(pr))
                for p, f, pr in zip(people, feats, probs, strict=True)
            ]
            t = 0.0
            filled = None
            asked = 0
            for c in order(ranked)[:MAX_ASKS]:
                asked += 1
                lat = w.latents[c.staff_id]
                p_true = p_accept_true(lat, day, shift, st.recent_30(c.staff_id, day))
                u = _unit(replicate, aid, c.staff_id, "accept")
                delay = 2 + int(_unit(replicate, aid, c.staff_id, "delay") * 18)  # 2 to 19 minutes
                if u < p_true and delay <= WINDOW_MIN:
                    t += delay
                    filled = c.staff_id
                    break
                declined = _unit(replicate, aid, c.staff_id, "kind") < 0.8
                t += delay if (declined and delay <= WINDOW_MIN) else WINDOW_MIN
            m.asks += asked
            if filled is None:
                m.escalated += 1
                st.holder[aid] = None
                continue
            m.filled += 1
            m.asks_filled += asked
            m.minutes_filled.append(t)
            m.covers[filled] += 1
            st.holder[aid] = filled
            st.cover_times[filled].append(now + timedelta(minutes=t))
            st.cover_days[filled].append(day)
    return m


def summarise(m: Metrics, population: list[str]) -> dict[str, Any]:
    """Return the reported metrics of one run."""
    return {
        "cascades": m.cascades,
        "escalation_rate": m.escalated / m.cascades if m.cascades else 0.0,
        "contacted_per_filled_gap": m.asks_filled / m.filled if m.filled else float("nan"),
        "time_to_fill_mean_min": float(np.mean(m.minutes_filled))
        if m.minutes_filled
        else float("nan"),
        "time_to_fill_median_min": float(np.median(m.minutes_filled))
        if m.minutes_filled
        else float("nan"),
        "cover_burden_gini": gini([float(m.covers.get(p, 0)) for p in population]),
        "covers_total": m.filled,
    }
