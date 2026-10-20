"""An independent hard-rule check of a published month, written against the Parquet output only.

Deliberately separate from the generator's own checks (synthdata.roster) and from the future
C2 validator: it reads the rules, times and qualifications from the data, not from the code.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
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


class Data:
    def __init__(self, root: Path) -> None:
        self.root = root

    def t(self, name: str) -> pl.DataFrame:
        return pl.read_parquet(self.root / f"{name}.parquet")


def effective_assignments(
    data: Data, month: date, now: datetime
) -> dict[tuple[str, date], set[str]]:
    """Published assignments of a month with accepted swaps and covers applied."""
    run = data.t("planning/roster_run").filter(pl.col("roster_month") == month)
    variant = data.t("planning/roster_variant").filter(pl.col("run_id").is_in(run["id"].implode()))
    a = data.t("planning/assignment").filter(pl.col("variant_id").is_in(variant["id"].implode()))
    owner = {r["id"]: (r["staff_id"], r["date"], r["shift_type"]) for r in a.iter_rows(named=True)}
    cur = dict(owner)
    for s in (
        data.t("operations/swap_offer")
        .filter(pl.col("status") == "accepted")
        .sort("accepted_at")
        .iter_rows(named=True)
    ):
        if s["assignment_id"] in cur and s["accepted_at"] <= now:
            _, d, c = cur[s["assignment_id"]]
            cur[s["assignment_id"]] = (s["accepted_by"], d, c)
    out: dict[tuple[str, date], set[str]] = defaultdict(set)
    cascades = (
        data.t("operations/cover_cascade").filter(pl.col("opened_at") <= now).sort("opened_at")
    )
    covered = {r["assignment_id"]: r for r in cascades.iter_rows(named=True)}  # the latest wins
    for aid, (sid, d, c) in cur.items():
        cas = covered.get(aid)
        if cas is not None:
            if cas["covered_by"] is not None:
                out[(cas["covered_by"], d)].add(c)
            continue
        out[(sid, d)].add(c)
    return dict(out)


def check_month(root: Path, month: date, published_at: datetime) -> list[Problem]:
    data = Data(root)
    last = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    rs = (
        data.t("organization/rule_set")
        .filter(pl.col("effective_from") <= month)
        .sort("effective_from")
    )
    rules = json.loads(rs["rules"][-1])
    st = {r["code"]: r for r in data.t("organization/shift_type").iter_rows(named=True)}
    holidays = set(data.t("organization/holiday")["date"].to_list())
    contracts = data.t("organization/contract")
    quals = data.t("organization/staff_qualification")
    rotations = data.t("organization/staff_rotation")

    def role(s: str, d: date) -> tuple[str, float] | None:
        c = contracts.filter(
            (pl.col("staff_id") == s)
            & (pl.col("valid_from") <= d)
            & (pl.col("valid_to").is_null() | (pl.col("valid_to") >= d))
        )
        return None if c.is_empty() else (c["role"][0], c["weekly_hours"][0])

    def has(s: str, q: str, d: date) -> bool:
        return not quals.filter(
            (pl.col("staff_id") == s)
            & (pl.col("qualification") == q)
            & (pl.col("valid_from") <= d)
            & (pl.col("valid_to").is_null() | (pl.col("valid_to") >= d))
        ).is_empty()

    def rotating(s: str, d: date) -> bool:
        return not rotations.filter(
            (pl.col("staff_id") == s) & (pl.col("start_date") <= d) & (pl.col("end_date") >= d)
        ).is_empty()

    def span(d: date, c: str) -> tuple[datetime, datetime]:
        s = st[c]
        start = datetime.combine(d, s["start_time"], tzinfo=BERLIN)
        end = datetime.combine(
            d + timedelta(days=1) if s["ends_next_day"] else d, s["end_time"], tzinfo=BERLIN
        )
        return start.astimezone(UTC), end.astimezone(UTC)

    plan = effective_assignments(data, month, published_at)
    prev_month = (month - timedelta(days=1)).replace(day=1)
    before = effective_assignments(data, prev_month, published_at)
    sched: dict[str, dict[date, set[str]]] = defaultdict(dict)
    for (s, d), cs in [*before.items(), *plan.items()]:
        sched[s].setdefault(d, set()).update(cs)

    # Blocked days: approved leave, declared unavailability in the month's window, known sickness.
    blocked: dict[str, set[date]] = defaultdict(set)
    leave: dict[str, set[date]] = defaultdict(set)
    for r in (
        data.t("requests/leave_request")
        .filter(pl.col("status") == "approved")
        .iter_rows(named=True)
    ):
        for d in _days(r["start_date"], r["end_date"]):
            leave[r["staff_id"]].add(d)
            blocked[r["staff_id"]].add(d)
    win = data.t("requests/request_window").filter(pl.col("roster_month") == month)["id"][0]
    for r in (
        data.t("requests/preference")
        .filter((pl.col("window_id") == win) & (pl.col("kind") == "unavailable"))
        .iter_rows(named=True)
    ):
        blocked[r["staff_id"]].add(r["date"])
    for r in (
        data.t("operations/absence")
        .filter(pl.col("reported_at") <= published_at)
        .iter_rows(named=True)
    ):
        blocked[r["staff_id"]].update(_days(r["start_date"], r["end_date"]))

    problems: list[Problem] = []
    # Coverage per day, shift and qualification.
    demand = data.t("organization/shift_demand").filter(
        (pl.col("date") >= month) & (pl.col("date") <= last)
    )
    for r in demand.iter_rows(named=True):
        d, c, q, n = r["date"], r["shift_type"], r["qualification"], r["required_count"]
        holders = [s for s, sp in sched.items() if c in sp.get(d, set())]
        have = len(holders) if q == "any" else sum(has(s, q, d) for s in holders)
        if have < n:
            problems.append(Problem("coverage", None, d, f"{c}/{q} {have}<{n}"))

    for s, sp in sched.items():
        weekends: set[date] = set()
        n_b = n_r = 0
        hours = 0.0
        ends: list[datetime] = []
        for d in _days(month - timedelta(days=7), last):
            cs = sp.get(d, set())
            working = sorted(cs & WORKING)
            for c in working:
                start, end = span(d, c)
                if (
                    d >= month
                    and ends
                    and (start - ends[-1]).total_seconds() / 3600 < rules["min_rest_hours"]
                ):
                    problems.append(Problem("min_rest", s, d, c))
                ends.append(end)
            if d < month or not cs:
                continue
            r = role(s, d)
            if r is None or rotating(s, d):
                problems.append(Problem("not_rostered", s, d, ",".join(cs)))
                continue
            if not cs <= ROLE_SHIFTS[r[0]]:
                problems.append(Problem("role", s, d, ",".join(cs)))
            if len(working) > 1 or ("ruf" in cs and set(working) - {"frueh"}):
                problems.append(Problem("one_shift_per_day", s, d, ",".join(sorted(cs))))
            if d in blocked[s]:
                problems.append(Problem("unavailable", s, d, ",".join(cs)))
            if "nacht" in cs and not has(s, "nachtdienstfaehig", d):
                problems.append(Problem("qualification", s, d, "nacht"))
            if "bereitschaft" in cs and not has(s, "nachtdienstfaehig", d):
                problems.append(Problem("qualification", s, d, "bereitschaft"))
            if "ruf" in cs and not has(s, "oberarzt", d):
                problems.append(Problem("qualification", s, d, "ruf"))
            if rules["free_day_after_on_call"] and "bereitschaft" in sp.get(
                d - timedelta(days=1), set()
            ):
                problems.append(Problem("free_day_after_on_call", s, d, ",".join(cs)))
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
                hours += {"frueh": 8.0, "spaet": 8.0, "nacht": float(st["nacht"]["net_hours"])}.get(
                    c, 0.0
                )
                if c == "bereitschaft":
                    hours += rules["bereitschaft_credited_hours"]
        if len(weekends) > rules["max_weekends_per_month"]:
            problems.append(Problem("max_weekends", s, month, str(len(weekends))))
        if n_b > rules["max_on_call_per_month"]:
            problems.append(Problem("max_on_call", s, month, str(n_b)))
        if n_r > rules["max_on_call_home_per_month"]:
            problems.append(Problem("max_on_call_home", s, month, str(n_r)))
        # Contract-hours band, for residents, specialists and seniors.
        target = credited = 0.0
        banded = False
        workdays = 0
        for d in _days(month, last):
            r = role(s, d)
            if r is None or rotating(s, d) or d.weekday() >= 5 or d in holidays:
                continue
            banded |= r[0] != "chefaerztin"
            workdays += 1
            target += r[1] / 5
            if d in leave[s]:
                credited += r[1] / 5
        if banded and target > 0 and workdays >= rules["contract_hours_band_min_days"]:
            lo, hi = rules["contract_hours_band"]
            ratio = (hours + credited) / target
            if not lo - 1e-9 <= ratio <= hi + 1e-9:
                problems.append(Problem("contract_hours_band", s, month, f"{ratio:.2f}"))
    return problems
