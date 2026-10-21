"""The rules, checked one person and one day at a time.

Rule values come from the rule set (``MonthInput.rules``); clock times, net hours and
qualification requirements from the data. Times are real Europe/Berlin timestamps, so rest
periods across a daylight-saving change are measured correctly.
"""

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dienstpilot_validator.model import Assignment, MonthInput, Person, Violation

VERSION = "c2-1.0.0"
BERLIN = ZoneInfo("Europe/Berlin")
WORKING = frozenset({"frueh", "spaet", "nacht", "bereitschaft"})
# Which roles may hold which shift (synthdata ASSUMPTIONS §6).
ROLE_SHIFTS: dict[str, frozenset[str]] = {
    "chefaerztin": frozenset({"ruf"}),
    "oberarzt": frozenset({"frueh", "ruf"}),
    "facharzt": WORKING,
    "assistenzarzt": WORKING,
}
RULE_KEYS = (
    "coverage",
    "one_shift_per_day",
    "min_rest",
    "max_consecutive_nights",
    "max_weekends",
    "max_on_call",
    "max_on_call_home",
    "free_day_after_on_call",
    "contract_hours_band",
    "qualification",
    "role",
    "unavailable",
    "not_rostered",
)
FIX = {
    "coverage": "fix.coverage",
    "one_shift_per_day": "fix.one_shift_per_day",
    "min_rest": "fix.min_rest",
    "max_consecutive_nights": "fix.max_consecutive_nights",
    "max_weekends": "fix.max_weekends",
    "max_on_call": "fix.max_on_call",
    "max_on_call_home": "fix.max_on_call_home",
    "free_day_after_on_call": "fix.free_day_after_on_call",
    "contract_hours_band": "fix.contract_hours_band",
    "qualification": "fix.qualification",
    "role": "fix.role",
    "unavailable": "fix.unavailable",
    "not_rostered": "fix.not_rostered",
}


def _v(rule: str, staff: str | None, day: date, **params: Any) -> Violation:
    """Build a violation; the fix text takes the same parameters as the message."""
    return Violation(f"violation.{rule}", staff, day, params, FIX[rule], dict(params))


def _days(a: date, b: date) -> Iterable[date]:
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def month_end(m: date) -> date:
    """Return the last day of the month starting at m."""
    return (m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _span(inp: MonthInput, d: date, code: str) -> tuple[datetime, datetime]:
    st = inp.shift_types[code]
    assert st.start is not None and st.end is not None
    start = datetime.combine(d, st.start, tzinfo=BERLIN)
    end = datetime.combine(d + timedelta(days=1) if st.ends_next_day else d, st.end, tzinfo=BERLIN)
    return start.astimezone(UTC), end.astimezone(UTC)


def _schedule(assignments: Iterable[Assignment]) -> dict[str, dict[date, set[str]]]:
    out: dict[str, dict[date, set[str]]] = {}
    for a in assignments:
        out.setdefault(a.staff_id, {}).setdefault(a.day, set()).add(a.shift_type)
    return out


def validate(inp: MonthInput, *, staff: Iterable[str] | None = None, days: Iterable[date] | None = None) -> list[Violation]:
    """Return every violation in the month (optionally only for some people and coverage days)."""
    sched = _schedule(inp.assignments)
    first, last = inp.month, month_end(inp.month)
    out: list[Violation] = []
    cover_days = sorted(set(days)) if days is not None else list(_days(first, last))
    for d in cover_days:
        out += _coverage(inp, sched, d)
    people = list(staff) if staff is not None else sorted(set(sched) | {
        p for p, person in inp.people.items() if any(person.contract_on(d) for d in (first, last))})
    for s in people:
        person = inp.people.get(s)
        if person is None:
            continue
        out += _person(inp, person, sched.get(s, {}), first, last)
    return out


def validate_change(
    inp: MonthInput, remove: Iterable[Assignment] = (), add: Iterable[Assignment] = ()
) -> tuple[list[Violation], list[Violation]]:
    """Validate a change: return (violations after the change, violations the change introduces).

    Only the people and days the change touches are re-checked, which keeps live editing fast.
    """
    removed, added = set(remove), list(add)
    changed = replace(inp, assignments=tuple(a for a in inp.assignments if a not in removed) + tuple(added))
    staff = {a.staff_id for a in (*removed, *added)}
    days = {a.day for a in (*removed, *added) if inp.month <= a.day <= month_end(inp.month)}
    before = {_key(v) for v in validate(inp, staff=staff, days=days)}
    after = validate(changed, staff=staff, days=days)
    return after, [v for v in after if _key(v) not in before]


def _key(v: Violation) -> tuple[str, str | None, date, str]:
    return v.key, v.staff_id, v.day, str(v.params.get("shift", "")) + "/" + str(v.params.get("qualification", ""))


def _coverage(inp: MonthInput, sched: dict[str, dict[date, set[str]]], d: date) -> list[Violation]:
    out = []
    for shift, qual, required in inp.demand.get(d, []):
        holders = [s for s, sp in sched.items() if shift in sp.get(d, set())]
        if qual == "any":
            have = len(holders)
        else:
            have = sum(1 for s in holders if s in inp.people and inp.people[s].has(qual, d))
        if have < required:
            out.append(_v("coverage", None, d, shift=shift, qualification=qual, required=required, assigned=have,
                          date=d.isoformat()))
    return out


def _person(inp: MonthInput, p: Person, sp: dict[date, set[str]], first: date, last: date) -> list[Violation]:
    rules = inp.rules
    mix: dict[str, dict[str, str]] = rules.get("qualification_mix", {})
    out: list[Violation] = []
    leave = inp.leave.get(p.id, frozenset())
    blocked = inp.blocked.get(p.id, frozenset()) | leave
    weekends: set[date] = set()
    n_b = n_r = 0
    hours = 0.0
    prev_end: datetime | None = None
    for d in _days(first - timedelta(days=7), last):
        cs = sp.get(d, set())
        working = sorted(cs & WORKING, key=lambda c: _span(inp, d, c)[0])
        for c in working:
            start, end = _span(inp, d, c)
            if d >= first and prev_end is not None:
                rest = (start - prev_end).total_seconds() / 3600
                if rest < rules["min_rest_hours"]:
                    out.append(_v("min_rest", p.id, d, shift=c, hours=round(rest, 1), required=rules["min_rest_hours"],
                                  date=d.isoformat()))
            prev_end = end
        if d < first or not cs:
            continue
        contract = p.contract_on(d)
        if contract is None or p.rotating(d):
            out.append(_v("not_rostered", p.id, d, shifts=sorted(cs), date=d.isoformat()))
            continue
        role = contract[0]
        if not cs <= ROLE_SHIFTS[role]:
            out.append(_v("role", p.id, d, role=role, shifts=sorted(cs - ROLE_SHIFTS[role]), date=d.isoformat()))
        if len(working) > 1 or ("ruf" in cs and set(working) - {"frueh"}):
            out.append(_v("one_shift_per_day", p.id, d, shifts=sorted(cs), date=d.isoformat()))
        if d in blocked:
            out.append(_v("unavailable", p.id, d, reason="leave" if d in leave else "unavailable",
                          shifts=sorted(cs), date=d.isoformat()))
        for c in sorted(cs):
            need = mix.get(c, {}).get("all")
            if need and not p.has(need, d):
                out.append(_v("qualification", p.id, d, shift=c, qualification=need, date=d.isoformat()))
        if rules["free_day_after_on_call"] and "bereitschaft" in sp.get(d - timedelta(days=1), set()):
            out.append(_v("free_day_after_on_call", p.id, d, shifts=sorted(cs), date=d.isoformat()))
        if "nacht" in cs:
            run, k = 1, d - timedelta(days=1)
            while "nacht" in sp.get(k, set()):
                run, k = run + 1, k - timedelta(days=1)
            if run > rules["max_consecutive_nights"]:
                out.append(_v("max_consecutive_nights", p.id, d, nights=run, max=rules["max_consecutive_nights"],
                              date=d.isoformat()))
        if d.weekday() >= 5:
            weekends.add(d - timedelta(days=d.weekday() - 5))
        n_b += "bereitschaft" in cs
        n_r += "ruf" in cs
        for c in cs:
            if c == "bereitschaft":
                hours += float(rules["bereitschaft_credited_hours"])
            elif c in WORKING:
                hours += inp.shift_types[c].net_hours
    if len(weekends) > rules["max_weekends_per_month"]:
        out.append(_v("max_weekends", p.id, first, weekends=len(weekends), max=rules["max_weekends_per_month"]))
    if n_b > rules["max_on_call_per_month"]:
        out.append(_v("max_on_call", p.id, first, count=n_b, max=rules["max_on_call_per_month"]))
    if n_r > rules["max_on_call_home_per_month"]:
        out.append(_v("max_on_call_home", p.id, first, count=n_r, max=rules["max_on_call_home_per_month"]))
    out += _band(inp, p, hours, first, last)
    return out


def contract_target(inp: MonthInput, p: Person, first: date, last: date) -> tuple[float, float, int, bool]:
    """Return (contract hours, leave credit, rostered workdays, band applies) for the month."""
    target = credited = 0.0
    workdays = 0
    banded = False
    leave = inp.leave.get(p.id, frozenset())
    for d in _days(first, last):
        c = p.contract_on(d)
        if c is None or p.rotating(d) or d.weekday() >= 5 or d in inp.holidays:
            continue
        banded |= c[0] != "chefaerztin"
        workdays += 1
        target += c[1] / 5
        if d in leave:
            credited += c[1] / 5
    return target, credited, workdays, banded and workdays >= inp.rules["contract_hours_band_min_days"]


def _band(inp: MonthInput, p: Person, hours: float, first: date, last: date) -> list[Violation]:
    target, credited, _, applies = contract_target(inp, p, first, last)
    if not applies or target <= 0:
        return []
    lo, hi = inp.rules["contract_hours_band"]
    ratio = (hours + credited) / target
    if lo - 1e-9 <= ratio <= hi + 1e-9:
        return []
    return [_v("contract_hours_band", p.id, first, percent=round(ratio * 100), low=round(lo * 100),
               high=round(hi * 100), hours=round(hours + credited, 2), contract_hours=round(target, 2))]
