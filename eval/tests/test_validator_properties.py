"""Property tests: rule-breaking changes are always caught, and both checkers agree on them."""

import time
from dataclasses import replace
from datetime import date, timedelta
from types import ModuleType
from typing import Any

import pytest
from dienstpilot_validator import Assignment, MonthInput, validate
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dienstpilot_eval.inputs import Data, month_end

from dienstpilot_eval.compare import from_checker, from_validator

MONTHS = [date(2024, 3, 1), date(2025, 7, 1), date(2025, 12, 1), date(2026, 10, 1), date(2026, 11, 1)]
SETTINGS = settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
WORKING = ("frueh", "spaet", "nacht", "bereitschaft")


def _month_days(m: date) -> list[date]:
    return [m + timedelta(days=i) for i in range((month_end(m) - m).days + 1)]


def _apply(inp: MonthInput, add: list[Assignment], remove: list[Assignment]) -> MonthInput:
    gone = set(remove)
    return replace(inp, assignments=tuple(a for a in inp.assignments if a not in gone) + tuple(add))


def _checker_on(checker: ModuleType, ds: Any, m: date, inp: MonthInput) -> Any:
    ds.plan[m] = [(a.staff_id, a.day, a.shift_type) for a in inp.assignments if a.day >= m]
    return checker.check_month(ds, m)


def _free(inp: MonthInput, staff: str, d: date) -> bool:
    return not any(a.staff_id == staff and a.day == d for a in inp.assignments)


@pytest.fixture(scope="module")
def months(data: Data) -> dict[date, MonthInput]:
    return {m: data.month(m).month for m in MONTHS}


def test_a_month_validates_fast_enough_for_live_editing(months: dict[date, MonthInput]) -> None:
    times = []
    for inp in months.values():
        for _ in range(10):
            t = time.perf_counter()
            validate(inp)
            times.append(time.perf_counter() - t)
    times.sort()
    p95 = times[int(0.95 * (len(times) - 1))]
    assert p95 < 0.050, f"p95 {p95 * 1000:.1f} ms"


MUTATIONS = ["rest", "double", "nights", "leave", "coverage", "unqualified", "weekends", "free_day", "on_call"]


@SETTINGS
@given(st.sampled_from(MONTHS), st.sampled_from(MUTATIONS), st.data())
def test_rule_breaking_changes_are_always_caught(months: dict[date, MonthInput], m: date, kind: str,
                                                 draw: st.DataObject) -> None:
    inp = months[m]
    days = _month_days(m)
    in_month = [a for a in inp.assignments if a.day >= m]
    pick = draw.draw
    add: list[Assignment] = []
    remove: list[Assignment] = []
    expect = kind
    if kind == "rest":
        late = [a for a in in_month if a.shift_type == "spaet" and a.day + timedelta(days=1) <= days[-1]
                and _free(inp, a.staff_id, a.day + timedelta(days=1))]
        a = pick(st.sampled_from(late))
        add, expect = [Assignment(a.staff_id, a.day + timedelta(days=1), "frueh")], "min_rest"
    elif kind == "double":
        a = pick(st.sampled_from([x for x in in_month if x.shift_type in ("frueh", "spaet")]))
        other = "spaet" if a.shift_type == "frueh" else "frueh"
        add, expect = [Assignment(a.staff_id, a.day, other)], "one_shift_per_day"
    elif kind == "nights":
        n = inp.rules["max_consecutive_nights"]
        a = pick(st.sampled_from([x for x in in_month if x.shift_type == "nacht" and x.day + timedelta(days=n) <= days[-1]]))
        add = [Assignment(a.staff_id, a.day + timedelta(days=i), "nacht") for i in range(1, n + 1)]
        remove = [x for x in inp.assignments if x.staff_id == a.staff_id and a.day < x.day <= a.day + timedelta(days=n)]
        expect = "max_consecutive_nights"
    elif kind == "leave":
        options = [(s, d) for s, ds in inp.leave.items() for d in ds if m <= d and d in days and inp.people[s].contract_on(d)
                   and not inp.people[s].rotating(d)]
        s, d = pick(st.sampled_from(sorted(options)))
        add, expect = [Assignment(s, d, "frueh")], "unavailable"
    elif kind == "coverage":
        tight = [a for a in in_month if a.shift_type in ("nacht", "bereitschaft", "ruf")]
        a = pick(st.sampled_from(tight))
        remove, expect = [a], "coverage"
    elif kind == "unqualified":
        options = [(s, d) for s, p in sorted(inp.people.items()) for d in days
                   if p.contract_on(d) and p.contract_on(d)[0] == "assistenzarzt"  # type: ignore[index]
                   and not p.rotating(d) and not p.has("nachtdienstfaehig", d)]
        if not options:
            return
        s, d = pick(st.sampled_from(options))
        remove = [x for x in inp.assignments if x.staff_id == s and x.day == d]
        add, expect = [Assignment(s, d, "nacht")], "qualification"
    elif kind == "weekends":
        sats = [d for d in days if d.weekday() == 5]
        s = pick(st.sampled_from(sorted({a.staff_id for a in in_month if inp.people[a.staff_id].contract_on(m)
                                         and inp.people[a.staff_id].contract_on(m)[0] == "assistenzarzt"})))  # type: ignore[index]
        add = [Assignment(s, d, "frueh") for d in sats if _free(inp, s, d)]
        remove = [x for x in inp.assignments if x.staff_id == s and x.day in sats and x.shift_type != "frueh"]
        add += [Assignment(s, x.day, "frueh") for x in remove]
        expect = "max_weekends"
    elif kind == "free_day":
        b = [a for a in in_month if a.shift_type == "bereitschaft" and a.day + timedelta(days=1) <= days[-1]
             and _free(inp, a.staff_id, a.day + timedelta(days=1))]
        a = pick(st.sampled_from(b))
        add, expect = [Assignment(a.staff_id, a.day + timedelta(days=1), "nacht")], "free_day_after_on_call"
    elif kind == "on_call":
        weekend_days = [d for d in days if d.weekday() >= 5]
        s = pick(st.sampled_from(sorted({a.staff_id for a in in_month if a.shift_type == "bereitschaft"})))
        add = [Assignment(s, d, "bereitschaft") for d in weekend_days if _free(inp, s, d)]
        expect = "max_on_call"
        if len(add) + sum(1 for a in in_month if a.staff_id == s and a.shift_type == "bereitschaft") <= inp.rules[
                "max_on_call_per_month"]:
            return
    mutated = _apply(inp, add, remove)
    found = {v.rule for v in validate(mutated)}
    if kind == "weekends" and len({d for d in days if d.weekday() == 5}) <= inp.rules["max_weekends_per_month"]:
        return
    assert expect in found, (kind, m, add[:3], remove[:3])


@SETTINGS
@given(st.sampled_from(MONTHS), st.data())
def test_both_checkers_agree_on_random_changes(months: dict[date, MonthInput], data: Data, checker: ModuleType,
                                               m: date, draw: st.DataObject) -> None:
    inp = months[m]
    days = _month_days(m)
    staff = sorted({a.staff_id for a in inp.assignments if a.day >= m})
    in_month = [a for a in inp.assignments if a.day >= m]
    adds = draw.draw(st.lists(st.tuples(st.sampled_from(staff), st.sampled_from(days), st.sampled_from(
        (*WORKING, "ruf"))), max_size=4))
    removes = draw.draw(st.lists(st.sampled_from(in_month), max_size=4, unique=True))
    mutated = _apply(inp, [Assignment(*x) for x in adds], removes)
    ds = checker.Dataset(data.root)
    assert from_validator(validate(mutated)) == from_checker(_checker_on(checker, ds, m, mutated))
