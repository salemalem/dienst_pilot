"""One measurement for any roster of a month, so the baseline and C1 are scored identically."""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, timedelta

from dienstpilot_validator import Assignment, validate
from dienstpilot_validator.validate import contract_target, month_end

from dienstpilot_eval.inputs import MonthData

WORKING = {"frueh", "spaet", "nacht", "bereitschaft"}


@dataclass(frozen=True)
class RosterMetrics:
    """What a roster achieves in a month."""

    hard_violations: int
    violations_by_rule: dict[str, int]
    wishes_total: int
    wishes_granted: int
    important_total: int
    important_granted: int
    burden_spread: int
    overtime_hours: float
    isolated_nights: int


def measure(md: MonthData, roster: tuple[Assignment, ...]) -> RosterMetrics:
    """Score a roster against the month's inputs (C2 counts the hard-rule violations)."""
    inp = replace(md.month, assignments=md.history + roster)
    violations = validate(inp)
    by_day: dict[tuple[str, date], set[str]] = {}
    for a in roster:
        by_day.setdefault((a.staff_id, a.day), set()).add(a.shift_type)
    granted = important = important_granted = 0
    for w in md.wishes:
        ok = any(w.shift_type in (None, s) for s in by_day.get((w.staff_id, w.day), set()))
        granted += ok
        important += w.important
        important_granted += ok and w.important
    first, last = md.month.month, month_end(md.month.month)
    loads = []
    for sid, p in md.month.people.items():
        c = p.contract_on(last) or p.contract_on(first)
        if c is None or c[0] not in ("facharzt", "assistenzarzt"):
            continue
        if not any(
            p.contract_on(first + timedelta(days=i)) and not p.rotating(first + timedelta(days=i))
            for i in range((last - first).days + 1)
        ):
            continue
        n0, w0, h0 = md.ytd.get(sid, (0, 0, 0))
        mine = [a for a in roster if a.staff_id == sid]
        nights = sum(a.shift_type == "nacht" for a in mine)
        weekends = len(
            {a.day - timedelta(days=a.day.weekday() - 5) for a in mine if a.day.weekday() >= 5}
        )
        hol = len({a.day for a in mine if a.day in md.month.holidays and a.shift_type in WORKING})
        loads.append(n0 + nights + w0 + weekends + h0 + hol)
    overtime = 0.0
    rules = md.month.rules
    for sid, p in md.month.people.items():
        target, credit, _, _ = contract_target(md.month, p, first, last)
        if target <= 0:
            continue
        hours = sum(
            float(rules["bereitschaft_credited_hours"])
            if a.shift_type == "bereitschaft"
            else md.month.shift_types[a.shift_type].net_hours
            if a.shift_type in WORKING
            else 0.0
            for a in roster
            if a.staff_id == sid
        )
        overtime += max(0.0, hours + credit - target)
    nights_held = {(a.staff_id, a.day) for a in (*md.history, *roster) if a.shift_type == "nacht"}
    isolated = sum(
        1
        for a in roster
        if a.shift_type == "nacht"
        and (a.staff_id, a.day - timedelta(days=1)) not in nights_held
        and (a.staff_id, a.day + timedelta(days=1)) not in nights_held
    )
    return RosterMetrics(
        len(violations),
        dict(Counter(v.rule for v in violations)),
        len(md.wishes),
        granted,
        important,
        important_granted,
        (max(loads) - min(loads)) if loads else 0,
        round(overtime, 2),
        isolated,
    )
