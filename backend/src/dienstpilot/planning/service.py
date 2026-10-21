"""Public interface of the planning context: published rosters, runs and proposals."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from dienstpilot.planning import models as m


@dataclass(frozen=True)
class Assignment:
    """A published assignment."""

    id: str
    staff_id: str
    day: date
    shift_type: str
    roster_month: date


@dataclass(frozen=True)
class PublishedRoster:
    """The published variant of a month and the versions that produced it."""

    roster_month: date
    run_id: str
    variant_id: str
    variant_label: str
    rule_set_version: str
    planner_kind: str
    generator_version: str | None
    published_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None


@dataclass(frozen=True)
class Proposal:
    """A proposal in the Planner's inbox."""

    id: str
    roster_month: date | None
    created_at: datetime
    created_by: str
    source: str
    title: str
    body: str
    status: str


def published_months(session: Session) -> list[date]:
    """Return the months that have a published roster, oldest first."""
    q = (
        select(m.RosterRun.roster_month)
        .join(m.RosterVariant, m.RosterVariant.run_id == m.RosterRun.id)
        .where(m.RosterVariant.status == "published")
        .distinct()
        .order_by(m.RosterRun.roster_month)
    )
    return list(session.scalars(q))


def published(session: Session, month: date) -> PublishedRoster | None:
    """Return the published roster of a month."""
    q = (
        select(m.RosterRun, m.RosterVariant)
        .join(m.RosterVariant, m.RosterVariant.run_id == m.RosterRun.id)
        .where(m.RosterRun.roster_month == month, m.RosterVariant.status == "published")
    )
    row = session.execute(q).first()
    if row is None:
        return None
    run, variant = row
    approval = session.scalar(select(m.Approval).where(m.Approval.variant_id == variant.id))
    return PublishedRoster(
        month,
        str(run.id),
        str(variant.id),
        variant.label,
        run.rule_set_version,
        run.planner_kind,
        run.generator_version,
        variant.published_at,
        None if approval is None else str(approval.approved_by),
        None if approval is None else approval.approved_at,
    )


def assignments(session: Session, start: date, end: date) -> list[Assignment]:
    """Return published assignments on days from start to end."""
    q = (
        select(m.Assignment, m.RosterRun.roster_month)
        .join(m.RosterVariant, m.RosterVariant.id == m.Assignment.variant_id)
        .join(m.RosterRun, m.RosterRun.id == m.RosterVariant.run_id)
        .where(
            m.RosterVariant.status == "published",
            m.Assignment.date >= start,
            m.Assignment.date <= end,
        )
    )
    return [
        Assignment(str(a.id), str(a.staff_id), a.date, a.shift_type, month)
        for a, month in session.execute(q)
    ]


def assignment(session: Session, assignment_id: str) -> Assignment | None:
    """Return one published assignment."""
    q = (
        select(m.Assignment, m.RosterRun.roster_month)
        .join(m.RosterVariant, m.RosterVariant.id == m.Assignment.variant_id)
        .join(m.RosterRun, m.RosterRun.id == m.RosterVariant.run_id)
        .where(m.Assignment.id == uuid.UUID(assignment_id))
    )
    row = session.execute(q).first()
    if row is None:
        return None
    a, month = row
    return Assignment(str(a.id), str(a.staff_id), a.date, a.shift_type, month)


def runs(session: Session, month: date) -> list[PublishedRoster]:
    """Return every run of a month with its variants (published or draft)."""
    q = (
        select(m.RosterRun, m.RosterVariant)
        .join(m.RosterVariant, m.RosterVariant.run_id == m.RosterRun.id)
        .where(m.RosterRun.roster_month == month)
    )
    out = []
    for run, v in session.execute(q):
        out.append(
            PublishedRoster(
                month,
                str(run.id),
                str(v.id),
                v.label,
                run.rule_set_version,
                run.planner_kind,
                run.generator_version,
                v.published_at,
                None,
                None,
            )
        )
    return out


def _proposal(p: m.Proposal) -> Proposal:
    return Proposal(
        str(p.id),
        p.roster_month,
        p.created_at,
        str(p.created_by),
        p.source,
        p.title,
        p.body,
        p.status,
    )


def proposals(session: Session, department_id: str, status: str | None = None) -> list[Proposal]:
    """Return proposals of a department, newest first."""
    q = select(m.Proposal).where(m.Proposal.department_id == uuid.UUID(department_id))
    if status is not None:
        q = q.where(m.Proposal.status == status)
    return [_proposal(p) for p in session.scalars(q.order_by(m.Proposal.created_at.desc()))]


def create_proposal(
    session: Session,
    *,
    department_id: str,
    roster_month: date | None,
    created_by: str,
    source: str,
    title: str,
    body: str,
    now: datetime,
) -> Proposal:
    """Create a proposal. It changes nothing until the Planner acts on it."""
    p = m.Proposal(
        id=uuid.uuid5(uuid.UUID(created_by), f"proposal/{title}/{now.isoformat()}"),
        department_id=uuid.UUID(department_id),
        roster_month=roster_month,
        created_at=now,
        created_by=uuid.UUID(created_by),
        source=source,
        title=title,
        body=body,
        status="open",
    )
    session.add(p)
    session.flush()
    return _proposal(p)


def decide_proposal(session: Session, proposal_id: str, accept: bool, now: datetime) -> Proposal:
    """Mark a proposal accepted or dismissed (acting on it is a separate, validated change)."""
    p = session.get(m.Proposal, uuid.UUID(proposal_id))
    if p is None:
        raise KeyError(proposal_id)
    if p.status != "open":
        raise ValueError("already decided")
    p.status = "accepted" if accept else "dismissed"
    p.decided_at = now
    session.flush()
    return _proposal(p)
