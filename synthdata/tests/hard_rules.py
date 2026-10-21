"""An independent hard-rule check of published months, written against the Parquet output only.

Deliberately separate from the generator's own checks (synthdata.roster) and from the future
C2 validator: it reads the rules, times and qualifications from the data, not from the code.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

BERLIN = ZoneInfo("Europe/Berlin")
WORKING = {"frueh", "spaet", "nacht", "bereitschaft"}
ROLE_SHIFTS = {
    "chefaerztin": {"ruf"},
    "oberarzt": {"frueh", "ruf"},
    "facharzt": WORKING,
    "assistenzarzt": WORKING,
}


@dataclass(frozen=True)
class Problem:
    rule: str
    staff: str | None
    day: date
    detail: str


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _month_end(m: date) -> date:
    return (m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


Interval = tuple[date, date | None]


def _covers(iv: Interval, d: date) -> bool:
    return iv[0] <= d and (iv[1] is None or d <= iv[1])


class Dataset:
    """The output of one generator run, indexed for checking."""

    def __init__(self, root: Path) -> None:
        def t(name: str) -> pl.DataFrame:
            return pl.read_parquet(root / f"{name}.parquet")

        self.rule_sets = [
            (r["effective_from"], json.loads(r["rules"]))
            for r in t("organization/rule_set").sort("effective_from").iter_rows(named=True)
        ]
        self.shift_types = {
            r["code"]: r for r in t("organization/shift_type").iter_rows(named=True)
        }
        self.holidays = set(t("organization/holiday")["date"].to_list())
        self.contracts: dict[str, list[tuple[Interval, str, float]]] = defaultdict(list)
        for r in t("organization/contract").iter_rows(named=True):
            self.contracts[r["staff_id"]].append(
                ((r["valid_from"], r["valid_to"]), r["role"], r["weekly_hours"])
            )
        self.quals: dict[tuple[str, str], list[Interval]] = defaultdict(list)
        for r in t("organization/staff_qualification").iter_rows(named=True):
            self.quals[(r["staff_id"], r["qualification"])].append((r["valid_from"], r["valid_to"]))
        self.rotations: dict[str, list[Interval]] = defaultdict(list)
        for r in t("organization/staff_rotation").iter_rows(named=True):
            self.rotations[r["staff_id"]].append((r["start_date"], r["end_date"]))
        self.demand = t("organization/shift_demand")

        runs = t("planning/roster_run")
        variants = t("planning/roster_variant").join(
            runs.select(pl.col("id").alias("run_id"), "roster_month"), on="run_id"
        )
        self.published_at: dict[date, datetime] = dict(
            zip(variants["roster_month"].to_list(), variants["published_at"].to_list(), strict=True)
        )
        a = t("planning/assignment").join(
            variants.select(pl.col("id").alias("variant_id"), "roster_month"), on="variant_id"
        )
        self.assignment: dict[str, tuple[str, date, str]] = {
            r["id"]: (r["staff_id"], r["date"], r["shift_type"]) for r in a.iter_rows(named=True)
        }
        self.plan: dict[date, list[tuple[str, date, str]]] = defaultdict(list)
        for r in a.iter_rows(named=True):
            self.plan[r["roster_month"]].append((r["staff_id"], r["date"], r["shift_type"]))
        self.swaps = (
            t("operations/swap_offer").filter(pl.col("status") == "accepted").sort("accepted_at")
        )
        self.cascades = t("operations/cover_cascade").sort("opened_at")

        self.leave: dict[str, set[date]] = defaultdict(set)
        for r in (
            t("requests/leave_request").filter(pl.col("status") == "approved").iter_rows(named=True)
        ):
            self.leave[r["staff_id"]].update(_days(r["start_date"], r["end_date"]))
        windows = dict(
            zip(
                t("requests/request_window")["id"].to_list(),
                t("requests/request_window")["roster_month"].to_list(),
                strict=True,
            )
        )
        self.unavailable: dict[tuple[date, str], set[date]] = defaultdict(set)
        prefs = t("requests/preference").filter(pl.col("kind") == "unavailable")
        for r in prefs.iter_rows(named=True):
            self.unavailable[(windows[r["window_id"]], r["staff_id"])].add(r["date"])
        self.absences = [
            (r["staff_id"], r["start_date"], r["end_date"], r["reported_at"])
            for r in t("operations/absence").iter_rows(named=True)
        ]
        self.effective_final = self._effective()

    def rules_for(self, month: date) -> dict[str, Any]:
        return [r for start, r in self.rule_sets if start <= month][-1]

    def role(self, s: str, d: date) -> tuple[str, float] | None:
        for iv, role, hours in self.contracts.get(s, []):
            if _covers(iv, d):
                return role, hours
        return None

    def has(self, s: str, q: str, d: date) -> bool:
        return any(_covers(iv, d) for iv in self.quals.get((s, q), []))

    def rotating(self, s: str, d: date) -> bool:
        return any(_covers(iv, d) for iv in self.rotations.get(s, []))

    def span(self, d: date, c: str) -> tuple[datetime, datetime]:
        st = self.shift_types[c]
        start = datetime.combine(d, st["start_time"], tzinfo=BERLIN)
        end_day = d + timedelta(days=1) if st["ends_next_day"] else d
        end = datetime.combine(end_day, st["end_time"], tzinfo=BERLIN)
        return start.astimezone(UTC), end.astimezone(UTC)

    def _effective(self) -> dict[str, dict[date, set[str]]]:
        """Every published assignment with all accepted swaps and covers applied (as worked)."""
        holder = {aid: s for aid, (s, _, _) in self.assignment.items()}
        events = [
            (r["accepted_at"], "swap", r["assignment_id"], r["accepted_by"])
            for r in self.swaps.iter_rows(named=True)
        ]
        events += [
            (r["opened_at"], "cover", r["assignment_id"], r["covered_by"])
            for r in self.cascades.iter_rows(named=True)
        ]
        for _, _, aid, to in sorted(events, key=lambda e: (e[0], e[1])):
            holder[aid] = to
        out: dict[str, dict[date, set[str]]] = defaultdict(dict)
        for aid, (_, d, c) in self.assignment.items():
            if holder[aid] is not None:
                out[holder[aid]].setdefault(d, set()).add(c)
        return out


def check_month(ds: Dataset, month: date) -> list[Problem]:
    """Every hard-rule problem of a month's roster as published.

    The days before the month come from the previous month as finally worked, which is the
    state the published month follows on from.
    """
    last = _month_end(month)
    rules = ds.rules_for(month)
    published_at = ds.published_at[month]
    sched: dict[str, dict[date, set[str]]] = defaultdict(dict)
    for s, sp in ds.effective_final.items():
        for d, cs in sp.items():
            if month - timedelta(days=7) <= d < month:
                sched[s][d] = set(cs)
    for s, d, c in ds.plan[month]:
        sched[s].setdefault(d, set()).add(c)

    blocked: dict[str, set[date]] = defaultdict(set)
    for s, a, b, reported in ds.absences:
        if reported <= published_at and b >= month and a <= last:
            blocked[s].update(_days(a, b))

    problems: list[Problem] = []
    for r in ds.demand.filter((pl.col("date") >= month) & (pl.col("date") <= last)).iter_rows(
        named=True
    ):
        d, c, q, n = r["date"], r["shift_type"], r["qualification"], r["required_count"]
        holders = [s for s, sp in sched.items() if c in sp.get(d, set())]
        have = len(holders) if q == "any" else sum(ds.has(s, q, d) for s in holders)
        if have < n:
            problems.append(Problem("coverage", None, d, f"{c}/{q}"))

    for s, sp in sched.items():
        unavailable = ds.leave[s] | ds.unavailable[(month, s)] | blocked[s]
        weekends: set[date] = set()
        n_b = n_r = 0
        hours = 0.0
        prev_end: datetime | None = None
        for d in _days(month - timedelta(days=7), last):
            cs = sp.get(d, set())
            for c in sorted(cs & WORKING, key=lambda c: ds.span(d, c)[0]):
                start, end = ds.span(d, c)
                rest = None if prev_end is None else (start - prev_end).total_seconds() / 3600
                if d >= month and rest is not None and rest < rules["min_rest_hours"]:
                    problems.append(Problem("min_rest", s, d, c))
                prev_end = end
            if d < month or not cs:
                continue
            role = ds.role(s, d)
            if role is None or ds.rotating(s, d):
                problems.append(Problem("not_rostered", s, d, ",".join(sorted(cs))))
                continue
            working = cs & WORKING
            if not cs <= ROLE_SHIFTS[role[0]]:
                problems.append(Problem("role", s, d, ",".join(sorted(cs))))
            if len(working) > 1 or ("ruf" in cs and working - {"frueh"}):
                problems.append(Problem("one_shift_per_day", s, d, ",".join(sorted(cs))))
            if d in unavailable:
                problems.append(Problem("unavailable", s, d, ",".join(sorted(cs))))
            for c, q in (
                ("nacht", "nachtdienstfaehig"),
                ("bereitschaft", "nachtdienstfaehig"),
                ("ruf", "oberarzt"),
            ):
                if c in cs and not ds.has(s, q, d):
                    problems.append(Problem("qualification", s, d, c))
            if rules["free_day_after_on_call"] and "bereitschaft" in sp.get(
                d - timedelta(days=1), set()
            ):
                problems.append(Problem("free_day_after_on_call", s, d, ",".join(sorted(cs))))
            if "nacht" in cs:
                run, k = 1, d - timedelta(days=1)
                while "nacht" in sp.get(k, set()):
                    run, k = run + 1, k - timedelta(days=1)
                if run > rules["max_consecutive_nights"]:
                    problems.append(Problem("max_consecutive_nights", s, d, str(run)))
            if d.weekday() >= 5:
                weekends.add(d - timedelta(days=d.weekday() - 5))
            n_b += "bereitschaft" in cs
            n_r += "ruf" in cs
            for c in cs:
                if c == "bereitschaft":
                    hours += rules["bereitschaft_credited_hours"]
                elif c in WORKING:
                    hours += float(ds.shift_types[c]["net_hours"])
        if len(weekends) > rules["max_weekends_per_month"]:
            problems.append(Problem("max_weekends", s, month, str(len(weekends))))
        if n_b > rules["max_on_call_per_month"]:
            problems.append(Problem("max_on_call", s, month, str(n_b)))
        if n_r > rules["max_on_call_home_per_month"]:
            problems.append(Problem("max_on_call_home", s, month, str(n_r)))
        # Contract-hours band (residents, specialists, seniors), with credited leave.
        target = credited = 0.0
        banded, workdays = False, 0
        for d in _days(month, last):
            role = ds.role(s, d)
            if role is None or ds.rotating(s, d) or d.weekday() >= 5 or d in ds.holidays:
                continue
            banded |= role[0] != "chefaerztin"
            workdays += 1
            target += role[1] / 5
            if d in ds.leave[s]:
                credited += role[1] / 5
        if banded and target > 0 and workdays >= rules["contract_hours_band_min_days"]:
            lo, hi = rules["contract_hours_band"]
            ratio = (hours + credited) / target
            if not lo - 1e-9 <= ratio <= hi + 1e-9:
                problems.append(Problem("contract_hours_band", s, month, f"{ratio:.2f}"))
    return problems


def check_all(root: Path) -> dict[date, list[Problem]]:
    """Problems of every published month."""
    ds = Dataset(root)
    return {m: check_month(ds, m) for m in sorted(ds.published_at)}
