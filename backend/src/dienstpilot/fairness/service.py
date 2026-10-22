"""Public interface of the fairness context: the burden of nights, weekends and holidays.

Pure functions over assignments (the application layer supplies them) and, from Phase 9, the
persisted month-end reports.
"""

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean, median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dienstpilot.fairness import models as m

WORKING = {"frueh", "spaet", "nacht", "bereitschaft"}
CATEGORIES = ("nights", "weekends", "holidays")


@dataclass(frozen=True)
class Burden:
    """Counts of one person in a period."""

    nights: int = 0
    weekends: int = 0
    holidays: int = 0

    def get(self, category: str) -> int:
        """Return the count of a category."""
        return int(getattr(self, category))


@dataclass(frozen=True)
class Distribution:
    """Department statistics of one category, without names."""

    category: str
    people: int
    mean: float
    median: float
    minimum: int
    maximum: int
    values: tuple[int, ...]  # sorted, anonymous


def burden(assignments: Iterable[tuple[str, date, str]], holidays: set[date]) -> dict[str, Burden]:
    """Count nights, weekends with any duty, and public holidays with a working shift per person."""
    nights: dict[str, int] = {}
    weekends: dict[str, set[date]] = {}
    hol: dict[str, set[date]] = {}
    for staff_id, d, shift in assignments:
        if shift == "nacht":
            nights[staff_id] = nights.get(staff_id, 0) + 1
        if d.weekday() >= 5:
            weekends.setdefault(staff_id, set()).add(d - timedelta(days=d.weekday() - 5))
        if d in holidays and shift in WORKING:
            hol.setdefault(staff_id, set()).add(d)
    people = set(nights) | set(weekends) | set(hol)
    return {
        p: Burden(nights.get(p, 0), len(weekends.get(p, set())), len(hol.get(p, set())))
        for p in people
    }


def distribution(counts: dict[str, Burden], people: Iterable[str], category: str) -> Distribution:
    """Department statistics of a category over the given people (zero if they had none)."""
    values = sorted(counts.get(p, Burden()).get(category) for p in people)
    if not values:
        return Distribution(category, 0, 0.0, 0.0, 0, 0, ())
    return Distribution(
        category,
        len(values),
        round(mean(values), 2),
        float(median(values)),
        values[0],
        values[-1],
        tuple(values),
    )


# --- month-end reports (persisted) ------------------------------------------------------------


@dataclass(frozen=True)
class MonthReportView:
    """A stored month-end report."""

    roster_month: date
    status: str  # prepared | closed
    prepared_at: datetime
    closed_at: datetime | None
    closed_by: str | None
    report_hash: str
    payload: dict[str, Any]


def _view(r: m.MonthReport) -> MonthReportView:
    return MonthReportView(
        r.roster_month,
        r.status,
        r.prepared_at,
        r.closed_at,
        None if r.closed_by is None else str(r.closed_by),
        r.report_hash,
        dict(r.payload),
    )


def payload_hash(payload: dict[str, Any]) -> str:
    """Return the SHA-256 of a report's canonical JSON."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def month_report(session: Session, department_id: str, month: date) -> MonthReportView | None:
    """Return the stored report of a month, if it was prepared."""
    r = session.get(m.MonthReport, (uuid.UUID(department_id), month))
    return None if r is None else _view(r)


def closed_months(session: Session, department_id: str) -> list[date]:
    """Return the months the Planner has closed, oldest first."""
    return list(
        session.scalars(
            select(m.MonthReport.roster_month)
            .where(
                m.MonthReport.department_id == uuid.UUID(department_id),
                m.MonthReport.status == "closed",
            )
            .order_by(m.MonthReport.roster_month)
        )
    )


def save_prepared(
    session: Session, department_id: str, month: date, payload: dict[str, Any], at: datetime
) -> MonthReportView:
    """Store the prepared report (once; a stored report is never replaced)."""
    key = (uuid.UUID(department_id), month)
    r = session.get(m.MonthReport, key)
    if r is None:
        r = m.MonthReport(
            department_id=key[0],
            roster_month=month,
            status="prepared",
            prepared_at=at,
            report_hash=payload_hash(payload),
            payload=payload,
        )
        session.add(r)
        session.flush()
    return _view(r)


def close_month(
    session: Session, department_id: str, month: date, by: str, at: datetime
) -> MonthReportView:
    """Lock a prepared report: it becomes final and the payroll export is released."""
    r = session.get(m.MonthReport, (uuid.UUID(department_id), month), with_for_update=True)
    if r is None:
        raise KeyError(month.isoformat())
    if r.status == "closed":
        raise ValueError("the month is already closed")
    r.status, r.closed_at, r.closed_by = "closed", at, uuid.UUID(by)
    session.flush()
    return _view(r)


def month_reports(session: Session, department_id: str) -> list[tuple[date, str]]:
    """Return (month, status) of every stored report, newest first."""
    rows = session.execute(
        select(m.MonthReport.roster_month, m.MonthReport.status)
        .where(m.MonthReport.department_id == uuid.UUID(department_id))
        .order_by(m.MonthReport.roster_month.desc())
    )
    return [(month, status) for month, status in rows]
