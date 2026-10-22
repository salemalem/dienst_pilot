"""C6 labels: simulated leave requests answered by the product's own M5 decision.

Every request is a draw from the protocol in ``ml/leave_surrogate/PROMOTION_RULE.md`` (seed,
strata, windows, state at submission). The answer comes from ``dienstpilot_solver.coverability``,
the function the check job runs, with the solver (C1) and validator (C2) on the synthetic data of
that month. Nothing here reads ``_truth/``. Labels hold facts and counts, never a staff id.
"""

import random
import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
from dienstpilot_eval.inputs import Data, month_end, to_problem
from dienstpilot_ml.features.leave import LeaveFacts, build_facts
from dienstpilot_solver.coverability import (
    CHECK_CONFIG,
    Callbacks,
    days,
    decide,
)
from dienstpilot_solver.model import Config, Problem, Result
from dienstpilot_solver.solve import VERSION as SOLVER_VERSION
from dienstpilot_solver.solve import solve
from dienstpilot_validator import VERSION as VALIDATOR_VERSION
from dienstpilot_validator import Assignment, validate

SEED = 20261020
TRAIN_MONTHS = [date(y, m, 1) for y in range(2021, 2025) for m in range(1, 13)]
TEST_MONTHS = [date(2025, m, 1) for m in range(1, 13)]
PER_MONTH = {"train": 62, "test": 83}
BLOCK_DAYS = (5, 10, 15)  # working days, probabilities 0.4, 0.4, 0.2
BLOCK_P = (0.4, 0.4, 0.2)
FIRST_MONTH = date(2021, 1, 1)
LABEL_VERSION = "c6-labels-1"


@dataclass(frozen=True)
class Spec:
    """One request to draw: its identity is (split, month, index)."""

    split: str
    month: date
    index: int

    @property
    def id(self) -> str:
        """Return the stable id used as the cache key."""
        return f"{self.split}|{self.month.isoformat()}|{self.index}"


def specs(split: str, per_month: int | None = None) -> list[Spec]:
    """Return every request of a split, in a fixed order."""
    months = TRAIN_MONTHS if split == "train" else TEST_MONTHS
    n = per_month or PER_MONTH[split]
    return [Spec(split, m, j) for m in months for j in range(n)]


def pilot_order(all_specs: list[Spec]) -> list[Spec]:
    """Return the specs in a fixed pseudo-random order (the pilot is the head of this list)."""
    out = list(all_specs)
    random.Random(f"{SEED}|pilot").shuffle(out)
    return out


@dataclass
class _Req:
    staff: str
    start: date
    end: date
    submitted: datetime
    status: str
    decided: datetime | None


class World:
    """The synthetic data, loaded once per process, with per-month problems cached."""

    def __init__(self, root: Path) -> None:
        """Load the dataset (labels need the tables of ``dienstpilot_eval.inputs`` and leave)."""
        self.data = Data(root)
        t = pl.read_parquet(root / "requests" / "leave_request.parquet")
        self.requests = [
            _Req(
                r["staff_id"],
                r["start_date"],
                r["end_date"],
                r["submitted_at"],
                r["status"],
                r["decided_at"],
            )
            for r in t.iter_rows(named=True)
        ]
        sh = pl.read_parquet(root / "organization" / "school_holiday.parquet")
        self.school: set[date] = set()
        for r in sh.iter_rows(named=True):
            self.school |= days(r["start_date"], r["end_date"])
        self._base: dict[date, Problem] = {}

    def base(self, m: date) -> Problem:
        """Return the month's problem with no leave, wishes, unavailability or history.

        Nothing of that exists 60 days ahead (the previous month is not worked yet), as in the
        product at the time of a request.
        """
        if m not in self._base:
            p = to_problem(self.data.month(m))
            self._base[m] = replace(p, leave={}, blocked={}, wishes=(), history=())
        return self._base[m]


def _window(rnd: random.Random, month: date) -> tuple[date, date]:
    n = rnd.choices(BLOCK_DAYS, BLOCK_P)[0]
    last = month_end(month)
    mondays = []
    d = month
    while d <= last:
        end = d + timedelta(days=(n // 5 - 1) * 7 + 4)
        if d.weekday() == 0 and end <= last:
            mondays.append((d, end))
        d += timedelta(days=1)
    return rnd.choice(mondays)


def _state(w: World, t: datetime) -> tuple[dict[str, set[date]], dict[str, set[date]]]:
    """Return (approved, pending) leave days at the moment t, per person."""
    approved: dict[str, set[date]] = {}
    pending: dict[str, set[date]] = {}
    for r in w.requests:
        if r.submitted >= t or (
            r.status == "declined" and r.decided is not None and r.decided <= t
        ):
            continue
        done = r.status == "approved" and r.decided is not None and r.decided <= t
        (approved if done else pending).setdefault(r.staff, set()).update(days(r.start, r.end))
    return approved, pending


@dataclass
class Label:
    """A drawn request and the solver's answer."""

    spec: Spec
    stratum: str
    k_stress: int
    facts: LeaveFacts
    outcome: str
    reason: str | None
    impact: dict[str, Any] | None
    solves: int
    solve_seconds: float

    def to_json(self) -> dict[str, Any]:
        """Return the stored record (no identifiers)."""
        return {
            "id": self.spec.id,
            "split": self.spec.split,
            "month": self.spec.month.isoformat(),
            "stratum": self.stratum,
            "k_stress": self.k_stress,
            "facts": self.facts.to_json(),
            "outcome": self.outcome,
            "reason": self.reason,
            "impact": self.impact,
            "solves": self.solves,
            "solve_seconds": round(self.solve_seconds, 2),
        }


@dataclass
class Draw:
    """A drawn request: the facts' inputs and the state the solver sees."""

    spec: Spec
    stratum: str
    k_stress: int
    start: date
    end: date
    requester: str
    submitted: datetime
    approved: dict[str, set[date]]
    pending: dict[str, set[date]]
    facts_args: dict[str, Any]

    def facts(self) -> LeaveFacts:
        """Return the facts the model sees (the shared definition)."""
        return build_facts(**self.facts_args)


def draw(w: World, spec: Spec) -> Draw:
    """Draw the request of ``spec`` from the protocol (no solver involved)."""
    rnd = random.Random(f"{SEED}|{spec.id}")
    start, end = _window(rnd, spec.month)
    stratum = "natural" if spec.index % 2 == 0 else "stress"
    notice = rnd.randint(60, 150)
    t = datetime.combine(start - timedelta(days=notice), datetime.min.time(), tzinfo=UTC).replace(
        hour=12
    )
    approved, pending = _state(w, t)
    base = w.base(spec.month)
    window = days(start, end)
    free = sorted(s for s, doc in base.doctors.items() if all(doc.available(d) for d in window))
    own = [s for s in free if not (approved.get(s, set()) | pending.get(s, set())) & window]
    me = rnd.choice(own)
    k = 0
    if stratum == "stress":
        k = rnd.randint(1, 10)
        for s in rnd.sample([s for s in free if s != me], k):
            (approved if rnd.random() < 0.5 else pending).setdefault(s, set()).update(window)
    facts_args: dict[str, Any] = dict(
        start=start,
        end=end,
        notice_days=notice,
        requester=me,
        doctors=base.doctors,
        approved=approved,
        pending=pending,
        demand=base.demand,
        holidays=base.holidays,
        school_days=w.school,
    )
    return Draw(spec, stratum, k, start, end, me, t, approved, pending, facts_args)


def label(w: World, spec: Spec, cfg: Config = CHECK_CONFIG) -> Label:
    """Draw the request of ``spec`` and answer it with the M5 decision."""
    dr = draw(w, spec)
    facts = dr.facts()
    start, end, me, t = dr.start, dr.end, dr.requester, dr.submitted
    approved, pending, stratum, k = dr.approved, dr.pending, dr.stratum, dr.k_stress
    first, last = spec.month, month_end(spec.month)
    in_month = {
        s: ds & days(first, last) for s, ds in pending.items() if s != me and ds & days(first, last)
    }
    memo: dict[Any, Result] = {}
    spent: dict[str, float] = {"n": 0.0, "s": 0.0}

    def problem(m: date, extra: dict[str, set[date]] | None) -> Problem:
        lo, hi = m - timedelta(days=7), month_end(m)
        leave = {s: set(ds & days(lo, hi)) for s, ds in approved.items()}
        for s, ds in (extra or {}).items():
            leave.setdefault(s, set()).update(ds)
        return replace(w.base(m), leave={s: frozenset(ds) for s, ds in leave.items() if ds})

    def run(p: Problem) -> Result:
        key = (p.month, frozenset(p.leave.items()), p.commitments)
        if key not in memo:
            t0 = time.perf_counter()
            memo[key] = solve(p, cfg)
            spent["n"] += 1
            spent["s"] += time.perf_counter() - t0
        return memo[key]

    def month_open(m: date) -> bool:
        pub = w.data.published_at.get(m)
        return m >= FIRST_MONTH and pub is not None and pub > t

    def valid(m: date, assignments: tuple[tuple[str, date, str], ...]) -> bool:
        p = problem(m, None)
        inp = w.data.month(m).month
        leave = {s: ds for s, ds in p.leave.items()}
        month = replace(
            inp,
            leave=leave,
            blocked={},
            assignments=tuple(Assignment(s, d, c) for s, d, c in assignments),
        )
        return not validate(month)

    cb = Callbacks(
        problem=problem,
        solve=run,
        month_open=month_open,
        valid=valid,
        weekend_limit=lambda m: int(w.data.rules_for(m)["max_weekends_per_month"]),
    )
    res = decide(cb, requester=me, start=start, end=end, pending=in_month, base={})
    return Label(
        spec,
        stratum,
        k,
        facts,
        res["outcome"],
        res.get("reason"),
        res.get("impact"),
        int(spent["n"]),
        spent["s"],
    )


VERSIONS = {"labels": LABEL_VERSION, "solver": SOLVER_VERSION, "validator": VALIDATOR_VERSION}
