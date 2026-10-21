"""The roster as worked: published assignments with swaps and cover applied, and hours."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from dienstpilot.operations import service as operations
from dienstpilot.organization import service as organization
from dienstpilot.organization.service import StaffMember
from dienstpilot.planning import service as planning
from dienstpilot.requests import service as requests
from dienstpilot.shared.settings import TZ

WORKING = ("frueh", "spaet", "nacht", "bereitschaft")


@dataclass(frozen=True)
class Shift:
    """A shift as it stands now (``holder`` None: nobody of the department holds it)."""

    assignment_id: str
    day: date
    shift_type: str
    holder: str | None
    planned_holder: str
    note: str  # planned | swap | cover | open | locum | unfilled | change


def month_start(d: date) -> date:
    """Return the first day of d's month."""
    return d.replace(day=1)


def month_end(d: date) -> date:
    """Return the last day of d's month."""
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def parse_month(text: str) -> date:
    """Parse 'YYYY-MM' into the first day of the month."""
    year, month = text.split("-")
    return date(int(year), int(month), 1)


def effective(session: Session, start: date, end: date, now: datetime | None = None) -> list[Shift]:
    """Return every published shift between start and end with its current holder.

    Swaps, cover and the Planner's changes (with reasons) apply on top of the published roster
    in the order they happened. A shift the Planner added has the change's id.
    """
    planned = planning.assignments(session, start, end)
    base = {a.id: a for a in planned}
    holder: dict[str, tuple[str | None, str]] = {a.id: (a.staff_id, "planned") for a in planned}
    events: list[tuple[datetime, int, str, str | None, str]] = [
        (h.at, 0, h.assignment_id, h.holder, h.note)
        for h in operations.holder_changes(session, list(holder))
    ]
    removed: set[str] = set()
    for ch in planning.changes(session, start, end):
        if ch.kind == "add":
            base[ch.id] = planning.Assignment(
                ch.id, ch.staff_after or "", ch.day, ch.shift_type, ch.roster_month
            )
            events.append((ch.changed_at, 1, ch.id, ch.staff_after, "change"))
        elif ch.assignment_id is not None:
            note = "removed" if ch.kind == "remove" else "change"
            events.append((ch.changed_at, 1, ch.assignment_id, ch.staff_after, note))
    for at, _, aid, who, note in sorted(events, key=lambda e: (e[0], e[1], e[2])):
        if now is not None and at > now:
            continue
        if note == "removed":
            removed.add(aid)
        else:
            removed.discard(aid)
            holder[aid] = (who, note)
    return sorted(
        (
            Shift(a.id, a.day, a.shift_type, holder[a.id][0], a.staff_id, holder[a.id][1])
            for a in base.values()
            if a.id in holder and a.id not in removed
        ),
        key=lambda s: (s.day, s.shift_type, s.assignment_id),
    )


def span(st: organization.ShiftType, day: date) -> tuple[datetime, datetime]:
    """Return start and end of a shift on a day (Europe/Berlin)."""
    assert st.start_time is not None and st.end_time is not None
    start = datetime.combine(day, st.start_time, tzinfo=TZ)
    end = datetime.combine(
        day + timedelta(days=1) if st.ends_next_day else day, st.end_time, tzinfo=TZ
    )
    return start, end


@dataclass(frozen=True)
class Hours:
    """A person's contract hours in a month."""

    month: date
    contract_hours: float
    leave_credit: float
    planned_hours: float  # credited hours of all shifts in the month
    worked_hours: float  # credited hours of shifts that ended by now
    overtime_hours: float  # planned + leave credit above the contract hours

    @property
    def ratio(self) -> float:
        """Return planned plus leave credit against contract hours."""
        return (
            (self.planned_hours + self.leave_credit) / self.contract_hours
            if self.contract_hours
            else 0.0
        )


def credit(shift_type: str, rules: dict[str, object]) -> float:
    """Return the hours a shift counts towards the contract."""
    if shift_type == "bereitschaft":
        return float(rules["bereitschaft_credited_hours"])  # type: ignore[arg-type]
    return {"frueh": 8.0, "spaet": 8.0, "nacht": 9.75}.get(shift_type, 0.0)


def hours_for(
    person: StaffMember,
    month: date,
    shifts: list[Shift],
    leave_days: set[date],
    holidays: set[date],
    rules: dict[str, object],
    types: dict[str, organization.ShiftType],
    now: datetime,
) -> Hours:
    """Return contract, planned, worked and overtime hours of one person in a month."""
    contract = leave = 0.0
    d = month
    while d <= month_end(month):
        c = person.contract_on(d)
        if c is not None and not person.on_rotation(d) and d.weekday() < 5 and d not in holidays:
            contract += c.weekly_hours / 5
            if d in leave_days:
                leave += c.weekly_hours / 5
        d += timedelta(days=1)
    planned = worked = 0.0
    for s in shifts:
        if s.holder != person.id or not (month <= s.day <= month_end(month)):
            continue
        h = credit(s.shift_type, rules)
        planned += h
        if s.shift_type in WORKING and span(types[s.shift_type], s.day)[1] <= now:
            worked += h
    overtime = max(0.0, planned + leave - contract)
    return Hours(
        month,
        round(contract, 2),
        round(leave, 2),
        round(planned, 2),
        round(worked, 2),
        round(overtime, 2),
    )


def approved_leave_days(
    session: Session, staff_ids: list[str], start: date, end: date
) -> dict[str, set[date]]:
    """Return approved leave days per person between start and end."""
    out: dict[str, set[date]] = {}
    for r in requests.leave_requests(
        session, staff_ids, status="approved", overlapping=(start, end)
    ):
        d = max(r.start_date, start)
        while d <= min(r.end_date, end):
            out.setdefault(r.staff_id, set()).add(d)
            d += timedelta(days=1)
    return out
