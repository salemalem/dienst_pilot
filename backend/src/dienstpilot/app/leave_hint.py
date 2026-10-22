"""The facts behind the instant leave hint (C6), from the department's state in the database.

The same definitions as the label generator: ``dienstpilot_ml.features.leave.build_facts``.
Pending requests of colleagues count as absence, as in the solver check.
"""

from datetime import date

from sqlalchemy.orm import Session

from dienstpilot.app.common import Department
from dienstpilot.app.engine_inputs import person
from dienstpilot.app.roster import approved_leave_days
from dienstpilot.organization import service as organization
from dienstpilot.requests import service as requests
from dienstpilot_ml.features.leave import LeaveFacts, build_facts
from dienstpilot_solver.model import Doctor


def facts_for(
    session: Session, dep: Department, requester: str, start: date, end: date, today: date
) -> LeaveFacts:
    """Return the counts around the window as the model sees them."""
    ids = list(dep.staff)
    approved = approved_leave_days(session, ids, start, end)
    pending: dict[str, set[date]] = {}
    for r in requests.leave_requests(session, ids, status="pending", overlapping=(start, end)):
        d = max(r.start_date, start)
        while d <= min(r.end_date, end):
            pending.setdefault(r.staff_id, set()).add(d)
            d = date.fromordinal(d.toordinal() + 1)
    doctors = {}
    for sid, member in dep.staff.items():
        p = person(member)
        doctors[sid] = Doctor(p.id, p.contracts, p.qualifications, p.rotations)
    return build_facts(
        start=start,
        end=end,
        notice_days=(start - today).days,
        requester=requester,
        doctors=doctors,
        approved=approved,
        pending=pending,
        demand=organization.demand(session, start, end),
        holidays=frozenset(organization.holidays(session, start, end)),
        school_days=organization.school_holiday_days(session, start, end),
    )
