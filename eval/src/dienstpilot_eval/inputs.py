"""Build engine inputs for a month from the synthetic Parquet output.

The same inputs go to the validator (C2) and the solver (C1), and the benchmark gives the
manual baseline and C1 exactly the same month: staff, contracts, rules, demand, approved leave,
declared unavailability, wishes, the previous month as worked, and the year-to-date ledger.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from dienstpilot_validator import Assignment, MonthInput, Person, ShiftType

if TYPE_CHECKING:
    from dienstpilot_solver.model import Problem

WORKING = {"frueh", "spaet", "nacht", "bereitschaft"}


def month_end(m: date) -> date:
    """Return the last day of the month starting at m."""
    return (m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


@dataclass(frozen=True)
class Wish:
    """A "möchte arbeiten" entry."""

    staff_id: str
    day: date
    shift_type: str | None
    important: bool


@dataclass(frozen=True)
class MonthData:
    """A month's inputs and what was published for it."""

    month: MonthInput  # with the published roster as assignments
    published: tuple[Assignment, ...]  # the month as published (baseline)
    history: tuple[Assignment, ...]  # the seven days before, as worked
    wishes: tuple[Wish, ...]
    ytd: dict[str, tuple[int, int, int]]  # staff → (nights, weekends, holidays) before the month
    published_at: datetime


class Data:
    """The synthetic dataset, loaded once."""

    def __init__(self, root: Path) -> None:
        """Load and index the tables the engines need."""
        self.root = root

        def t(name: str) -> pl.DataFrame:
            return pl.read_parquet(root / f"{name}.parquet")

        self.rule_sets = sorted(
            ((r["effective_from"], json.loads(r["rules"])) for r in t("organization/rule_set").iter_rows(named=True)),
            key=lambda x: x[0],
        )
        self.shift_types = {
            r["code"]: ShiftType(r["code"], r["start_time"], r["end_time"], r["ends_next_day"], float(r["net_hours"]))
            for r in t("organization/shift_type").iter_rows(named=True)
            if r["start_time"] is not None
        }
        self.holidays = frozenset(t("organization/holiday")["date"].to_list())
        contracts: dict[str, list[tuple[str, float, date, date | None]]] = {}
        for r in t("organization/contract").sort("valid_from").iter_rows(named=True):
            contracts.setdefault(r["staff_id"], []).append((r["role"], float(r["weekly_hours"]), r["valid_from"],
                                                            r["valid_to"]))
        quals: dict[str, list[tuple[str, date, date | None]]] = {}
        for r in t("organization/staff_qualification").iter_rows(named=True):
            quals.setdefault(r["staff_id"], []).append((r["qualification"], r["valid_from"], r["valid_to"]))
        rots: dict[str, list[tuple[date, date]]] = {}
        for r in t("organization/staff_rotation").iter_rows(named=True):
            rots.setdefault(r["staff_id"], []).append((r["start_date"], r["end_date"]))
        self.people = {s: Person(s, tuple(c), tuple(quals.get(s, [])), tuple(rots.get(s, []))) for s, c in contracts.items()}
        self.names = dict(zip(t("organization/staff")["id"].to_list(), t("organization/staff")["display_name"].to_list(),
                              strict=True))
        self.demand: dict[date, list[tuple[str, str, int]]] = {}
        for r in t("organization/shift_demand").iter_rows(named=True):
            self.demand.setdefault(r["date"], []).append((r["shift_type"], r["qualification"], r["required_count"]))

        runs = t("planning/roster_run")
        variants = t("planning/roster_variant").join(runs.select(pl.col("id").alias("run_id"), "roster_month"),
                                                    on="run_id")
        self.published_at = dict(zip(variants["roster_month"].to_list(), variants["published_at"].to_list(),
                                     strict=True))
        a = t("planning/assignment").join(variants.select(pl.col("id").alias("variant_id"), "roster_month"),
                                          on="variant_id")
        self.assignment = {r["id"]: (r["staff_id"], r["date"], r["shift_type"], r["roster_month"])
                           for r in a.iter_rows(named=True)}
        # As worked: published, then swaps and cover in time order.
        holder = {aid: v[0] for aid, v in self.assignment.items()}
        events = [(r["accepted_at"], 1, r["assignment_id"], r["accepted_by"])
                  for r in t("operations/swap_offer").filter(pl.col("status") == "accepted").iter_rows(named=True)]
        events += [(r["opened_at"], 0, r["assignment_id"], r["covered_by"])
                   for r in t("operations/cover_cascade").iter_rows(named=True)]
        for _, _, aid, to in sorted(events, key=lambda e: (e[0], e[1])):
            holder[aid] = to
        self.worked = [Assignment(h, v[1], v[2]) for aid, v in self.assignment.items() if (h := holder[aid])]

        self.leave: dict[str, set[date]] = {}
        for r in t("requests/leave_request").filter(pl.col("status") == "approved").iter_rows(named=True):
            self.leave.setdefault(r["staff_id"], set()).update(_days(r["start_date"], r["end_date"]))
        windows = dict(zip(t("requests/request_window")["id"].to_list(),
                           t("requests/request_window")["roster_month"].to_list(), strict=True))
        self.prefs = t("requests/preference").with_columns(
            pl.col("window_id").replace_strict(windows, return_dtype=pl.Date).alias("roster_month"))
        self.absences = [(r["staff_id"], r["start_date"], r["end_date"], r["reported_at"])
                         for r in t("operations/absence").iter_rows(named=True)]

    def rules_for(self, d: date) -> dict[str, Any]:
        """Return the rule set in effect on d."""
        rules: dict[str, Any] = [r for start, r in self.rule_sets if start <= d][-1]
        return rules

    def month(self, m: date, assignments: tuple[Assignment, ...] | None = None) -> MonthData:
        """Return a month's inputs; ``assignments`` replaces the published roster if given."""
        last = month_end(m)
        published_at = self.published_at[m]
        published = tuple(Assignment(s, d, c) for s, d, c, rm in self.assignment.values() if rm == m)
        history = tuple(a for a in self.worked if m - timedelta(days=7) <= a.day < m)
        blocked: dict[str, set[date]] = {}
        month_prefs = self.prefs.filter(pl.col("roster_month") == m)
        for r in month_prefs.filter(pl.col("kind") == "unavailable").iter_rows(named=True):
            blocked.setdefault(r["staff_id"], set()).add(r["date"])
        for s, a, b, reported in self.absences:
            if reported <= published_at and b >= m and a <= last:
                blocked.setdefault(s, set()).update(_days(a, b))
        leave = {s: frozenset(d for d in days if m - timedelta(days=7) <= d <= last) for s, days in self.leave.items()}
        wishes = tuple(Wish(r["staff_id"], r["date"], r["shift_type"], r["important"])
                       for r in month_prefs.filter(pl.col("kind") == "wish_work").iter_rows(named=True))
        inp = MonthInput(
            month=m, rules=self.rules_for(m), shift_types=self.shift_types, people=self.people,
            demand={d: self.demand.get(d, []) for d in _days(m, last)}, holidays=self.holidays,
            assignments=history + (published if assignments is None else assignments),
            leave=leave, blocked={s: frozenset(v) for s, v in blocked.items()},
        )
        return MonthData(inp, published, history, wishes, self.ytd(m), published_at)

    def ytd(self, m: date) -> dict[str, tuple[int, int, int]]:
        """Return the year-to-date ledger (nights, weekends, holidays) before month m, as worked."""
        start = date(m.year, 1, 1)
        nights: dict[str, int] = {}
        weekends: dict[str, set[date]] = {}
        hol: dict[str, set[date]] = {}
        for a in self.worked:
            if not (start <= a.day < m):
                continue
            if a.shift_type == "nacht":
                nights[a.staff_id] = nights.get(a.staff_id, 0) + 1
            if a.day.weekday() >= 5:
                weekends.setdefault(a.staff_id, set()).add(a.day - timedelta(days=a.day.weekday() - 5))
            if a.day in self.holidays and a.shift_type in WORKING:
                hol.setdefault(a.staff_id, set()).add(a.day)
        people = set(nights) | set(weekends) | set(hol)
        return {p: (nights.get(p, 0), len(weekends.get(p, set())), len(hol.get(p, set()))) for p in people}


def to_problem(md: MonthData, **overrides: Any) -> "Problem":
    """Turn a month's inputs into the optimizer's problem (same facts the baseline had)."""
    from dienstpilot_solver.model import Doctor, Problem, Shift, WishIn

    inp = md.month
    return Problem(
        month=inp.month,
        rules=inp.rules,
        shifts={c: Shift(c, s.start, s.end, s.ends_next_day, s.net_hours)  # type: ignore[arg-type]
                for c, s in inp.shift_types.items()},
        doctors={s: Doctor(s, p.contracts, p.qualifications, p.rotations) for s, p in inp.people.items()},
        demand=inp.demand,
        holidays=inp.holidays,
        leave=inp.leave,
        blocked=inp.blocked,
        history=tuple((a.staff_id, a.day, a.shift_type) for a in md.history),
        wishes=tuple(WishIn(w.staff_id, w.day, w.shift_type, w.important) for w in md.wishes),
        ytd=md.ytd,
        **overrides,
    )
