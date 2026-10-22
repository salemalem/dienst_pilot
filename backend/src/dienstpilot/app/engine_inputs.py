"""Inputs for the optimizer (C1) and the validator (C2), built from the bounded contexts.

Both engines see the same facts: staff with contract, qualification and rotation history, the
rule set in effect, demand, holidays, approved leave, declared unavailability, absences known
so far, and the seven days before the month as worked. The solver also gets the month's wishes,
the year-to-date burden ledger and promised trade-offs.
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from dienstpilot.app.common import Department
from dienstpilot.app.roster import Shift, approved_leave_days, effective, month_end
from dienstpilot.fairness import service as fairness
from dienstpilot.operations import service as operations
from dienstpilot.organization import service as organization
from dienstpilot.planning import service as planning
from dienstpilot.requests import service as requests
from dienstpilot_solver.model import AvoidIn, Commitment, Doctor, Problem, WishIn
from dienstpilot_solver.model import Shift as SolverShift
from dienstpilot_validator import Assignment, MonthInput, Person, ShiftType

HISTORY_DAYS = 7


def _days(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def person(p: organization.StaffMember) -> Person:
    """Return the validator's view of a physician."""
    return Person(
        p.id,
        tuple((c.role, c.weekly_hours, c.valid_from, c.valid_to) for c in p.contracts),
        p.qualifications,
        tuple((a, b) for a, b, _ in p.rotations),
    )


def held(shifts: list[Shift]) -> tuple[Assignment, ...]:
    """Return the assignments of shifts somebody of the department holds."""
    return tuple(Assignment(s.holder, s.day, s.shift_type) for s in shifts if s.holder)


@dataclass
class Inputs:
    """Builds and caches month inputs for one request or job."""

    session: Session
    dep: Department
    now: datetime
    _facts: dict[date, MonthInput] = field(default_factory=dict)

    def facts(self, m: date) -> MonthInput:
        """Return the month's facts without assignments (cached)."""
        if m in self._facts:
            return self._facts[m]
        s, last = self.session, month_end(m)
        first = m - timedelta(days=HISTORY_DAYS)
        types = {
            c: ShiftType(c, t.start_time, t.end_time, t.ends_next_day, t.net_hours)
            for c, t in organization.shift_types(s).items()
            if t.start_time is not None
        }
        ids = list(self.dep.staff)
        leave = approved_leave_days(s, ids, first, last)
        blocked: dict[str, set[date]] = {}
        window = requests.window_for(s, m)
        if window is not None:
            for e in requests.preferences(s, window.id):
                if e.kind == "unavailable":
                    blocked.setdefault(e.staff_id, set()).add(e.day)
        for a in operations.absences(s, ids, first, last):
            if a.reported_at <= self.now:
                blocked.setdefault(a.staff_id, set()).update(
                    _days(max(a.start_date, first), min(a.end_date, last))
                )
        demand = organization.demand(s, m, last)
        inp = MonthInput(
            month=m,
            rules=organization.rules_for(s, m).rules,
            shift_types=types,
            people={p.id: person(p) for p in self.dep.staff.values()},
            demand={d: demand.get(d, []) for d in _days(m, last)},
            holidays=frozenset(organization.holidays(s, first, last)),
            assignments=(),
            leave={k: frozenset(v) for k, v in leave.items()},
            blocked={k: frozenset(v) for k, v in blocked.items()},
        )
        self._facts[m] = inp
        return inp

    def history(self, m: date) -> tuple[Assignment, ...]:
        """Return the seven days before the month as worked (published roster with changes)."""
        return held(
            effective(self.session, m - timedelta(days=HISTORY_DAYS), m - timedelta(days=1))
        )

    def month(self, m: date, assignments: tuple[Assignment, ...] | None = None) -> MonthInput:
        """Return the month with assignments (default: the published roster as it stands)."""
        if assignments is None:
            assignments = held(effective(self.session, m, month_end(m)))
        return replace(self.facts(m), assignments=self.history(m) + assignments)

    def variant(self, variant_id: str) -> MonthInput:
        """Return the month of a draft (or published) variant with its own assignments."""
        info = planning.variant(self.session, variant_id)
        if info is None:
            raise KeyError(variant_id)
        own = tuple(
            Assignment(a.staff_id, a.day, a.shift_type)
            for a in planning.variant_assignments(self.session, variant_id)
        )
        return self.month(info[1], own)

    def ytd(self, m: date) -> dict[str, tuple[int, int, int]]:
        """Return the burden ledger (nights, weekends, holidays) from 1 January to before m."""
        start = date(m.year, 1, 1)
        if m == start:
            return {}
        shifts = effective(self.session, start, m - timedelta(days=1), self.now)
        hol = set(organization.holidays(self.session, start, m))
        counts = fairness.burden(((s.holder, s.day, s.shift_type) for s in shifts if s.holder), hol)
        return {k: (b.nights, b.weekends, b.holidays) for k, b in counts.items()}

    def problem(
        self,
        m: date,
        *,
        extra_leave: dict[str, set[date]] | None = None,
        commitments: tuple[Commitment, ...] | None = None,
    ) -> Problem:
        """Return the solver's problem for a month (optionally with a hypothetical leave)."""
        facts = self.facts(m)
        leave = {k: set(v) for k, v in facts.leave.items()}
        for k, v in (extra_leave or {}).items():
            leave.setdefault(k, set()).update(v)
        window = requests.window_for(self.session, m)
        wishes = (
            tuple(
                WishIn(e.staff_id, e.day, e.shift_type, e.important)
                for e in requests.preferences(self.session, window.id)
                if e.kind == "wish_work" and e.staff_id in self.dep.staff
            )
            if window is not None
            else ()
        )
        avoid = (
            tuple(
                AvoidIn(e.staff_id, e.day, e.shift_type)
                for e in requests.preferences(self.session, window.id)
                if e.kind == "avoid_shift" and e.shift_type and e.staff_id in self.dep.staff
            )
            if window is not None
            else ()
        )
        if commitments is None:
            commitments = tuple(
                Commitment(sid, w) for sid, w in requests.trade_off_commitments(self.session, m)
            )
        return Problem(
            month=m,
            rules=facts.rules,
            shifts={
                c: SolverShift(c, t.start, t.end, t.ends_next_day, t.net_hours)  # type: ignore[arg-type]
                for c, t in facts.shift_types.items()
            },
            doctors={
                p.id: Doctor(p.id, p.contracts, p.qualifications, p.rotations)
                for p in facts.people.values()
            },
            demand=facts.demand,
            holidays=facts.holidays,
            leave={k: frozenset(v) for k, v in leave.items()},
            blocked=facts.blocked,
            history=tuple((a.staff_id, a.day, a.shift_type) for a in self.history(m)),
            wishes=wishes,
            avoid=avoid,
            ytd=self.ytd(m),
            commitments=commitments,
        )
