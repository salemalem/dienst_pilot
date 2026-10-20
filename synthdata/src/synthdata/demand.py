"""Demand templates: how many physicians each shift needs, with which qualification."""

from dataclasses import dataclass
from datetime import date

from synthdata.calendar import days, school_holiday_periods

# (shift, qualification or "any", count). Qualification rows are minimums within the total.
WEEKDAY: list[tuple[str, str, int]] = [
    ("frueh", "any", 10),
    ("spaet", "any", 5),
    ("nacht", "any", 2),
    ("nacht", "nachtdienstfaehig", 2),
    ("ruf", "any", 1),
    ("ruf", "oberarzt", 1),
]
WEEKEND_HOLIDAY: list[tuple[str, str, int]] = [
    ("frueh", "any", 2),
    ("bereitschaft", "any", 2),
    ("bereitschaft", "nachtdienstfaehig", 2),
    ("bereitschaft", "facharzt", 1),
    ("ruf", "any", 1),
    ("ruf", "oberarzt", 1),
]


@dataclass(frozen=True)
class Slot:
    """One position to fill: a shift on a day, with the qualifications the holder needs."""

    day: date
    shift: str
    needs: frozenset[str]


def _school_days() -> set[date]:
    out: set[date] = set()
    for y in range(2020, 2028):
        for a, b, _, _ in school_holiday_periods(y):
            out.update(days(a, b))
    return out


SCHOOL_DAYS = _school_days()


def template_for(d: date, holidays: set[date]) -> list[tuple[str, str, int]]:
    """Return the demand template that applies on d.

    Weekday day-shift demand is seasonal (assumption): fewer elective admissions in school
    holidays, more patients in the respiratory season (December to February).
    """
    if d.weekday() >= 5 or d in holidays:
        return WEEKEND_HOLIDAY
    if d in SCHOOL_DAYS:
        early, late = 8, 4
    elif d.month in (1, 2, 12):
        early, late = 10, 5
    else:
        early, late = 9, 5
    return [(s, q, early if s == "frueh" else late if s == "spaet" else c) for s, q, c in WEEKDAY]


def slots_for(d: date, holidays: set[date]) -> list[Slot]:
    """Expand a day's template into individual slots, hardest first (R, B, N, F, S).

    Each qualification minimum becomes that many slots that require it; the rest of the
    shift's total needs only the base qualification of the shift.
    """
    rows = template_for(d, holidays)
    out: list[Slot] = []
    for shift in ("ruf", "bereitschaft", "nacht", "frueh", "spaet"):
        total = sum(c for s, q, c in rows if s == shift and q == "any")
        if total == 0:
            continue
        base = {q for s, q, c in rows if s == shift and q != "any" and c == total}
        extras = [(q, c) for s, q, c in rows if s == shift and q != "any" and c < total]
        n = 0
        for q, c in extras:
            for _ in range(c):
                out.append(Slot(d, shift, frozenset(base | {q})))
                n += 1
        for _ in range(total - n):
            out.append(Slot(d, shift, frozenset(base)))
    return out
