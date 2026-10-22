"""Month end: the prepared documentation, the Planner's one-click close, the payroll export."""

import csv
import io
import json
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from dienstpilot.app.common import Department, department, record, settle_timers
from dienstpilot.app.context import CtxDep
from dienstpilot.app.deps import OversightReaderDep, PlannerDep
from dienstpilot.app.roster import parse_month
from dienstpilot.fairness import service as fairness
from dienstpilot.shared.workflows import engine, machines

router = APIRouter(tags=["month end"])
Month = Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]


class MonthRow(BaseModel):
    """One month with a prepared report."""

    roster_month: date
    status: str  # prepared | closed


class PersonMonth(BaseModel):
    """One physician's month (names are resolved here; the stored report holds ids only)."""

    staff_id: str
    display_name: str
    contract_hours: float
    leave_credit_hours: float
    planned_hours: float
    worked_hours: float
    overtime_hours: float
    rest_violations: int
    nights: int
    weekends: int
    holidays: int


class TrailEntry(BaseModel):
    """One entry of the decision trail."""

    seq: int
    at: datetime
    actor: str
    action: str
    subject_type: str


class Narrative(BaseModel):
    """Explanatory text. Until Phase 10 it is a labelled placeholder, not generated text."""

    engine: str
    text: str


class MonthReportOut(BaseModel):
    """The month-end report (Oversight and Planner)."""

    roster_month: date
    status: str
    prepared_at: datetime
    closed_at: datetime | None
    report_hash: str
    people: list[PersonMonth]
    total_overtime_hours: float
    rest_violations_total: int
    distributions: list[dict[str, Any]]
    decision_trail: list[TrailEntry]
    audit_head_seq: int
    narrative: Narrative
    payroll_released: bool


def _month(text: str) -> date:
    return parse_month(text)


def _report(c: CtxDep, month: date) -> fairness.MonthReportView:
    r = fairness.month_report(c.session, c.user.department_id, month)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No report for this month (yet)")
    return r


def _people(dep: Department, payload: dict[str, Any]) -> list[PersonMonth]:
    return [PersonMonth(display_name=dep.name(p["staff_id"]) or "", **p) for p in payload["people"]]


@router.get("/oversight/months")
def months(c: CtxDep, _: OversightReaderDep) -> list[MonthRow]:
    """Months whose documentation has been prepared, newest first."""
    settle_timers(c)
    return [
        MonthRow(roster_month=m, status=st)
        for m, st in fairness.month_reports(c.session, c.user.department_id)
    ]


@router.get("/oversight/months/{month}/report")
def month_report(c: CtxDep, _: OversightReaderDep, month: str) -> MonthReportOut:
    """Return the month-end report: hours, overtime, rest, burden and the decision trail."""
    settle_timers(c)
    m = _month(month)
    r = _report(c, m)
    dep, p = department(c), r.payload
    return MonthReportOut(
        roster_month=m,
        status=r.status,
        prepared_at=r.prepared_at,
        closed_at=r.closed_at,
        report_hash=r.report_hash,
        people=_people(dep, p),
        total_overtime_hours=p["total_overtime_hours"],
        rest_violations_total=p["rest_violations_total"],
        distributions=p["distributions"],
        decision_trail=[TrailEntry(**e) for e in p["decision_trail"]],
        audit_head_seq=p["audit_head"]["seq"],
        narrative=Narrative(engine=p["narrative"]["engine"], text=p["narrative"]["de"]),
        payroll_released=r.status == "closed",
    )


class Closed(BaseModel):
    """The month is closed."""

    roster_month: date
    status: str
    closed_at: datetime


@router.post("/planner/months/{month}/close")
def close_month(c: CtxDep, _: PlannerDep, month: str) -> Closed:
    """Confirm the prepared documentation with one click: locks the month, releases payroll."""
    settle_timers(c)
    m = _month(month)
    _report(c, m)
    assert c.user.staff_id is not None
    try:
        r = fairness.close_month(c.session, c.user.department_id, m, c.user.id, c.clock.now())
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    engine.ensure(
        c.session,
        machines.MONTH_END,
        f"{c.user.department_id}:{m:%Y-%m}",
        "prepared",
        c.clock.now(),
    )
    engine.move(
        c.session, machines.MONTH_END, f"{c.user.department_id}:{m:%Y-%m}", "closed", c.clock.now()
    )
    record(
        c,
        "month.closed",
        "month_report",
        None,
        None,
        {"roster_month": m.isoformat(), "report_hash": r.report_hash},
    )
    assert r.closed_at is not None
    return Closed(roster_month=m, status=r.status, closed_at=r.closed_at)


@router.get("/oversight/months/{month}/payroll")
def payroll(
    c: CtxDep,
    _: OversightReaderDep,
    month: str,
    fmt: Annotated[str, Query(alias="format", pattern="^(json|csv)$")] = "json",
) -> Response:
    """Return the payroll export of a closed month (409 until the Planner has closed it)."""
    settle_timers(c)
    m = _month(month)
    r = _report(c, m)
    if r.status != "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, "The Planner has not closed this month yet")
    rows = [
        {
            "staff_id": p.staff_id,
            "name": p.display_name,
            "contract_hours": p.contract_hours,
            "leave_credit_hours": p.leave_credit_hours,
            "planned_hours": p.planned_hours,
            "worked_hours": p.worked_hours,
            "overtime_hours": p.overtime_hours,
            "nights": p.nights,
            "weekends": p.weekends,
            "holidays": p.holidays,
        }
        for p in _people(department(c), r.payload)
    ]
    if fmt == "csv":
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["staff_id"], delimiter=";")
        w.writeheader()
        w.writerows(rows)
        return Response(
            out.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="lohnexport-{m:%Y-%m}.csv"'},
        )
    return Response(
        json.dumps(
            {"roster_month": m.isoformat(), "report_hash": r.report_hash, "rows": rows},
            ensure_ascii=False,
        ),
        media_type="application/json",
    )
