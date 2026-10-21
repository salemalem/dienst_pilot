"""Inputs and outputs of the validator."""

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any


@dataclass(frozen=True)
class ShiftType:
    """A shift type as stored in the organization data."""

    code: str
    start: time | None
    end: time | None
    ends_next_day: bool
    net_hours: float


@dataclass(frozen=True)
class Person:
    """A physician's contracts, qualifications and rotations (all with validity)."""

    id: str
    contracts: tuple[tuple[str, float, date, date | None], ...]  # role, weekly hours, from, to
    qualifications: tuple[tuple[str, date, date | None], ...] = ()
    rotations: tuple[tuple[date, date], ...] = ()

    def contract_on(self, d: date) -> tuple[str, float] | None:
        """Return (role, weekly hours) on d, or None if not employed."""
        for role, hours, a, b in self.contracts:
            if a <= d and (b is None or d <= b):
                return role, hours
        return None

    def rotating(self, d: date) -> bool:
        """Return whether the physician is on an external rotation on d."""
        return any(a <= d <= b for a, b in self.rotations)

    def has(self, qualification: str, d: date) -> bool:
        """Return whether the physician holds the qualification on d."""
        return any(q == qualification and a <= d and (b is None or d <= b) for q, a, b in self.qualifications)


@dataclass(frozen=True)
class Assignment:
    """A physician holds a shift on a day."""

    staff_id: str
    day: date
    shift_type: str


@dataclass(frozen=True)
class MonthInput:
    """Everything the validator needs for one month.

    ``assignments`` holds the month and the seven days before it (rest periods and night runs
    continue across the month boundary). ``blocked`` are days a person may not work: approved
    leave, declared unavailability ("kann nicht") and known absences.
    """

    month: date
    rules: dict[str, Any]
    shift_types: dict[str, ShiftType]
    people: dict[str, Person]
    demand: dict[date, list[tuple[str, str, int]]]
    holidays: frozenset[date]
    assignments: tuple[Assignment, ...]
    leave: dict[str, frozenset[date]] = field(default_factory=dict)
    blocked: dict[str, frozenset[date]] = field(default_factory=dict)


@dataclass(frozen=True)
class Violation:
    """One broken hard rule, as an i18n key with parameters and a suggested fix."""

    key: str  # e.g. "violation.min_rest"
    staff_id: str | None
    day: date
    params: dict[str, Any]
    fix_key: str
    fix_params: dict[str, Any]

    @property
    def rule(self) -> str:
        """Return the rule name without the "violation." prefix."""
        return self.key.removeprefix("violation.")
