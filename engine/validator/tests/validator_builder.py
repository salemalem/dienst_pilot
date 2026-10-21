"""A tiny department for unit tests: built by hand, independent of the synthetic data."""

from datetime import date, time
from typing import Any

from dienstpilot_validator import Assignment, MonthInput, Person, ShiftType

RULES: dict[str, Any] = {
    "min_rest_hours": 11.0,
    "max_consecutive_nights": 3,
    "max_weekends_per_month": 2,
    "max_on_call_per_month": 4,
    "max_on_call_home_per_month": 10,
    "free_day_after_on_call": True,
    "contract_hours_band": [0.8, 1.1],
    "contract_hours_band_min_days": 5,
    "bereitschaft_credited_hours": 18.0,
    "qualification_mix": {
        "nacht": {"all": "nachtdienstfaehig"},
        "bereitschaft": {"all": "nachtdienstfaehig", "at_least_one": "facharzt"},
        "ruf": {"all": "oberarzt"},
    },
}
SHIFTS = {
    "frueh": ShiftType("frueh", time(7, 30), time(16, 0), False, 8.0),
    "spaet": ShiftType("spaet", time(13, 30), time(22, 0), False, 8.0),
    "nacht": ShiftType("nacht", time(21, 30), time(8, 0), True, 9.75),
    "bereitschaft": ShiftType("bereitschaft", time(8, 0), time(8, 0), True, 24.0),
    "ruf": ShiftType("ruf", time(16, 0), time(7, 30), True, 0.0),
}
OPEN = date(2010, 1, 1)


def person(pid: str, role: str = "assistenzarzt", hours: float = 40.0, quals: tuple[str, ...] = ("nachtdienstfaehig",),
           rotations: tuple[tuple[date, date], ...] = ()) -> Person:
    return Person(pid, ((role, hours, OPEN, None),), tuple((q, OPEN, None) for q in quals), rotations)


def month_input(month: date, assignments: list[tuple[str, date, str]], people: dict[str, Person] | None = None,
                demand: dict[date, list[tuple[str, str, int]]] | None = None, **kw: Any) -> MonthInput:
    people = people or {"a": person("a"), "b": person("b"), "s": person("s", "oberarzt", quals=("oberarzt", "facharzt",
                                                                                                "nachtdienstfaehig"))}
    return MonthInput(month=month, rules=kw.pop("rules", RULES), shift_types=SHIFTS, people=people,
                      demand=demand or {}, holidays=frozenset(kw.pop("holidays", ())),
                      assignments=tuple(Assignment(*a) for a in assignments), **kw)


def rules(violations: list[Any]) -> set[str]:
    return {v.rule for v in violations}
