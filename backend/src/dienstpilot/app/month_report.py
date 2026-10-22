"""Month-end documentation: hours, overtime, rest compliance, burden and the decision trail.

Prepared automatically once the month is over in demo time (the ``month.prepare`` timer); the
Planner then confirms it with one click, which locks it and releases the payroll export. Every
number comes from the same functions the screens use (``hours_table``, ``fairness.burden``);
nothing is typed in. The narrative is a labelled stand-in until the planner copilot (Phase 10).
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from dienstpilot.app.deps import Ctx
from dienstpilot.app.roster import effective, month_end, month_start
from dienstpilot.app.routes.me import hours_table
from dienstpilot.audit import service as audit
from dienstpilot.engines.registry import Engines
from dienstpilot.fairness import service as fairness
from dienstpilot.identity.service import UserView
from dienstpilot.organization import service as organization
from dienstpilot.planning import service as planning
from dienstpilot.recording import record
from dienstpilot.shared.clock import FixedClock
from dienstpilot.shared.settings import TZ
from dienstpilot.shared.workflows import engine, machines

NARRATIVE = {
    "engine": "stand-in",
    "de": "Platzhalter: Der erläuternde Text zu diesem Bericht folgt mit dem Planungs-Assistenten "
    "(Phase 10). Alle Zahlen stammen aus der Berechnung.",
    "en": "Placeholder: the explanatory text for this report follows with the planner copilot "
    "(phase 10). All figures come from the calculation.",
}
BANDED = ("facharzt", "assistenzarzt", "oberarzt")


def system_user(department_id: str) -> UserView:
    """Return the user the automatic preparation acts as (read-only, Oversight scope)."""
    return UserView("", "system", "System", "oversight", department_id, None)


def build(ctx: Ctx, month: date) -> dict[str, Any]:
    """Compute the report of a month as of the context's clock."""
    dep_id = ctx.user.department_id
    members = organization.staff(ctx.session, dep_id)
    end = month_end(month)
    people = sorted(
        (p for p in members if p.role_on(end) in BANDED or p.role_on(month) in BANDED),
        key=lambda p: p.display_name,
    )
    table = hours_table(ctx, month, [p.id for p in people], rest=True)
    shifts = [s for s in effective(ctx.session, month, end) if s.holder]
    holidays = set(organization.holidays(ctx.session, month, end))
    burden = fairness.burden(
        ((s.holder, s.day, s.shift_type) for s in shifts if s.holder), holidays
    )
    rota = [
        p.id
        for p in people
        if p.role_on(end) in ("facharzt", "assistenzarzt") and p.rostered_on(end)
    ]
    since = datetime.combine(month, datetime.min.time(), tzinfo=TZ)
    until = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    trail = audit.trail(ctx.session, dep_id, since, until - timedelta(microseconds=1))
    head_seq, head_hash = audit.head(ctx.session, dep_id)
    rows: list[dict[str, Any]] = []
    for p in people:
        h = table[p.id]
        b = burden.get(p.id, fairness.Burden())
        rows.append(
            {
                "staff_id": p.id,
                "contract_hours": h.contract_hours,
                "leave_credit_hours": h.leave_credit_hours,
                "planned_hours": h.planned_hours,
                "worked_hours": h.worked_hours,
                "overtime_hours": h.overtime_hours,
                "rest_violations": h.rest_compliance.violations if h.rest_compliance else 0,
                "nights": b.nights,
                "weekends": b.weekends,
                "holidays": b.holidays,
            }
        )
    return {
        "roster_month": month.isoformat(),
        "people": rows,
        "total_overtime_hours": round(sum(r["overtime_hours"] for r in rows), 2),
        "rest_violations_total": sum(r["rest_violations"] for r in rows),
        "distributions": [
            {
                "metric": d.category,
                "people": d.people,
                "mean": d.mean,
                "median": d.median,
                "minimum": d.minimum,
                "maximum": d.maximum,
            }
            for d in (fairness.distribution(burden, rota, cat) for cat in fairness.CATEGORIES)
        ],
        # The decision trail: who did what and when, from the hash-chained log (no payloads).
        "decision_trail": [
            {
                "seq": e.seq,
                "at": e.occurred_at.isoformat(),
                "actor": e.actor_label,
                "action": e.action,
                "subject_type": e.subject_type,
            }
            for e in trail
        ],
        "audit_head": {"seq": head_seq, "hash": head_hash},
        "validator": ctx.engines.validator.info.version,
        "narrative": NARRATIVE,
    }


def prepare(
    session: Session, engines: Engines, department_id: str, month: date, at: datetime
) -> bool:
    """Prepare and store a month's report; False when there is nothing to report or it exists."""
    if planning.published(session, month_start(month)) is None:
        return False
    if fairness.month_report(session, department_id, month) is not None:
        return False
    ctx = Ctx(session, FixedClock(at), engines, system_user(department_id))
    payload = build(ctx, month)
    fairness.save_prepared(session, department_id, month, payload, at)
    engine.ensure(session, machines.MONTH_END, f"{department_id}:{month:%Y-%m}", "waiting", at)
    engine.move(session, machines.MONTH_END, f"{department_id}:{month:%Y-%m}", "prepared", at)
    record(
        session,
        occurred_at=at,
        department_id=department_id,
        actor_user_id=None,
        actor_label="System",
        action="month.report_prepared",
        subject_type="month_report",
        payload={"roster_month": month.isoformat()},
    )
    return True
