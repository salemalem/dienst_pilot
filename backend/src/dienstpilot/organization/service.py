"""Public interface of the organization context.

Staff, contracts, qualifications, shift types, demand, holidays and rule sets. Read functions
return plain data; writes are explicit.
"""

import uuid
from dataclasses import dataclass
from datetime import date, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dienstpilot.organization import models as m


@dataclass(frozen=True)
class ContractPeriod:
    """A contract period of a physician."""

    role: str
    title_de: str
    title_en: str
    weekly_hours: float
    valid_from: date
    valid_to: date | None

    def covers(self, d: date) -> bool:
        """Return whether the period includes d."""
        return self.valid_from <= d and (self.valid_to is None or d <= self.valid_to)


@dataclass(frozen=True)
class StaffMember:
    """A physician with their whole contract, qualification and rotation history."""

    id: str
    display_name: str
    department_id: str
    contracts: tuple[ContractPeriod, ...]
    qualifications: tuple[tuple[str, date, date | None], ...]
    rotations: tuple[tuple[date, date, str], ...]

    def contract_on(self, d: date) -> ContractPeriod | None:
        """Return the contract period covering d."""
        return next((c for c in self.contracts if c.covers(d)), None)

    def role_on(self, d: date) -> str | None:
        """Return the role on d, or None if not employed."""
        c = self.contract_on(d)
        return None if c is None else c.role

    def on_rotation(self, d: date) -> bool:
        """Return whether the physician is on an external rotation on d."""
        return any(a <= d <= b for a, b, _ in self.rotations)

    def rostered_on(self, d: date) -> bool:
        """Return whether the physician is on the department's roster on d."""
        return self.role_on(d) is not None and not self.on_rotation(d)

    def qualified(self, qualification: str, d: date) -> bool:
        """Return whether the physician holds the qualification on d."""
        return any(
            q == qualification and a <= d and (b is None or d <= b)
            for q, a, b in self.qualifications
        )


@dataclass(frozen=True)
class ShiftType:
    """A shift type (UI_SPEC §5)."""

    code: str
    letter_de: str
    letter_en: str
    name_de: str
    name_en: str
    start_time: time | None
    end_time: time | None
    ends_next_day: bool
    net_hours: float
    kind: str
    burden_weight: float


@dataclass(frozen=True)
class RuleSetInfo:
    """A rule-set version."""

    id: str
    version: str
    effective_from: date
    rules: dict[str, Any]
    change_note_de: str
    change_note_en: str


def departments(session: Session) -> list[tuple[str, str]]:
    """Return (id, name) of every department."""
    return [(str(d.id), d.name) for d in session.scalars(select(m.Department))]


def department_name(session: Session, department_id: str) -> str:
    """Return a department's name."""
    d = session.get(m.Department, uuid.UUID(department_id))
    return "" if d is None else d.name


def staff(session: Session, department_id: str) -> list[StaffMember]:
    """Return every physician of the department (current and former), with their history."""
    dep = uuid.UUID(department_id)
    people = list(session.scalars(select(m.Staff).where(m.Staff.department_id == dep)))
    ids = [p.id for p in people]
    contracts: dict[uuid.UUID, list[ContractPeriod]] = {i: [] for i in ids}
    for c in session.scalars(
        select(m.Contract).where(m.Contract.staff_id.in_(ids)).order_by(m.Contract.valid_from)
    ):
        contracts[c.staff_id].append(
            ContractPeriod(
                c.role, c.title_de, c.title_en, float(c.weekly_hours), c.valid_from, c.valid_to
            )
        )
    quals: dict[uuid.UUID, list[tuple[str, date, date | None]]] = {i: [] for i in ids}
    for q in session.scalars(
        select(m.StaffQualification).where(m.StaffQualification.staff_id.in_(ids))
    ):
        quals[q.staff_id].append((q.qualification, q.valid_from, q.valid_to))
    rots: dict[uuid.UUID, list[tuple[date, date, str]]] = {i: [] for i in ids}
    for r in session.scalars(select(m.StaffRotation).where(m.StaffRotation.staff_id.in_(ids))):
        rots[r.staff_id].append((r.start_date, r.end_date, r.target))
    return sorted(
        (
            StaffMember(
                str(p.id),
                p.display_name,
                str(p.department_id),
                tuple(contracts[p.id]),
                tuple(quals[p.id]),
                tuple(rots[p.id]),
            )
            for p in people
        ),
        key=lambda s: s.display_name,
    )


def shift_types(session: Session) -> dict[str, ShiftType]:
    """Return the shift types by code."""
    return {
        s.code: ShiftType(
            s.code,
            s.letter_de,
            s.letter_en,
            s.name_de,
            s.name_en,
            s.start_time,
            s.end_time,
            s.ends_next_day,
            float(s.net_hours),
            s.kind,
            float(s.burden_weight),
        )
        for s in session.scalars(select(m.ShiftType))
    }


def demand(session: Session, start: date, end: date) -> dict[date, list[tuple[str, str, int]]]:
    """Return the demand rows (shift, qualification, count) per day."""
    out: dict[date, list[tuple[str, str, int]]] = {}
    q = select(m.ShiftDemand).where(m.ShiftDemand.date >= start, m.ShiftDemand.date <= end)
    for r in session.scalars(q):
        out.setdefault(r.date, []).append((r.shift_type, r.qualification, r.required_count))
    return out


def holidays(session: Session, start: date, end: date) -> dict[date, tuple[str, str]]:
    """Return public holidays (name DE, name EN) between start and end."""
    q = select(m.Holiday).where(m.Holiday.date >= start, m.Holiday.date <= end)
    return {h.date: (h.name_de, h.name_en) for h in session.scalars(q)}


def qualifications(session: Session) -> list[tuple[str, str, str]]:
    """Return (code, name DE, name EN) of every qualification."""
    return [(q.code, q.name_de, q.name_en) for q in session.scalars(select(m.Qualification))]


def rule_sets(session: Session) -> list[RuleSetInfo]:
    """Return all rule-set versions, oldest first."""
    rows = session.scalars(select(m.RuleSet).order_by(m.RuleSet.effective_from))
    return [
        RuleSetInfo(
            str(r.id),
            r.version,
            r.effective_from,
            dict(r.rules),
            r.change_note_de,
            r.change_note_en,
        )
        for r in rows
    ]


def rules_for(session: Session, d: date) -> RuleSetInfo:
    """Return the rule set in effect on d."""
    return [r for r in rule_sets(session) if r.effective_from <= d][-1]


def add_rule_set(
    session: Session,
    version: str,
    effective_from: date,
    rules: dict[str, Any],
    note_de: str,
    note_en: str,
) -> RuleSetInfo:
    """Add a new rule-set version (rules are data; old rosters keep their version)."""
    r = m.RuleSet(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"rule-set/{version}"),
        version=version,
        effective_from=effective_from,
        rules=rules,
        change_note_de=note_de,
        change_note_en=note_en,
    )
    session.add(r)
    session.flush()
    return RuleSetInfo(str(r.id), version, effective_from, rules, note_de, note_en)
