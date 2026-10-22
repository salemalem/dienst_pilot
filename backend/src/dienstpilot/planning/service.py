"""Public interface of the planning context: published rosters, runs and proposals."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

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


def assignments_of(session: Session, staff_id: str, until_month: date) -> list[Assignment]:
    """Return one person's published assignments in roster months up to ``until_month``."""
    q = (
        select(m.Assignment, m.RosterRun.roster_month)
        .join(m.RosterVariant, m.RosterVariant.id == m.Assignment.variant_id)
        .join(m.RosterRun, m.RosterRun.id == m.RosterVariant.run_id)
        .where(
            m.RosterVariant.status == "published",
            m.Assignment.staff_id == uuid.UUID(staff_id),
            m.RosterRun.roster_month <= until_month,
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


# --- C1 runs, draft variants, published-roster changes ------------------------------------------


@dataclass(frozen=True)
class Run:
    """A solver run and its variants."""

    id: str
    roster_month: date
    status: str
    created_at: datetime
    finished_at: datetime | None
    rule_set_version: str
    solver_version: str | None
    validator_version: str | None
    config: dict[str, Any] | None
    explanations: list[dict[str, Any]] | None
    error: str | None
    variants: tuple["VariantInfo", ...]


@dataclass(frozen=True)
class VariantInfo:
    """A variant of a run."""

    id: str
    label: str
    status: str
    profile: str | None
    metrics: dict[str, Any] | None
    recommended: bool
    published_at: datetime | None


@dataclass(frozen=True)
class Change:
    """A Planner's change to a published roster."""

    id: str
    roster_month: date
    kind: str
    assignment_id: str | None
    day: date
    shift_type: str
    staff_before: str | None
    staff_after: str | None
    reason: str
    changed_by: str
    changed_at: datetime


def create_run(
    session: Session, month: date, rule_set_version: str, requested_by: str, now: datetime
) -> str:
    """Queue a solver run for a month."""
    r = m.RosterRun(
        id=uuid.uuid4(),  # random: the demo clock can stand still between two runs
        roster_month=month,
        rule_set_version=rule_set_version,
        planner_kind="c1",
        generator_version=None,
        created_at=now,
        status="queued",
        requested_by=uuid.UUID(requested_by),
    )
    session.add(r)
    session.flush()
    return str(r.id)


def set_run_status(
    session: Session,
    run_id: str,
    status: str,
    *,
    now: datetime | None = None,
    solver_version: str | None = None,
    validator_version: str | None = None,
    config: dict[str, Any] | None = None,
    explanations: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> None:
    """Record a run's progress and outcome."""
    r = session.get(m.RosterRun, uuid.UUID(run_id))
    if r is None:
        raise KeyError(run_id)
    r.status = status
    if now is not None and status in ("done", "infeasible", "failed"):
        r.finished_at = now
    for k, v in (
        ("solver_version", solver_version),
        ("validator_version", validator_version),
        ("config", config),
        ("explanations", explanations),
        ("error", error),
    ):
        if v is not None:
            setattr(r, k, v)
    session.flush()


def add_variant(
    session: Session,
    run_id: str,
    label: str,
    profile: str,
    metrics: dict[str, Any],
    recommended: bool,
    assignments: list[tuple[str, date, str]],
) -> str:
    """Store a draft variant and its assignments."""
    vid = uuid.uuid5(uuid.UUID(run_id), f"variant/{label}")
    session.add(
        m.RosterVariant(
            id=vid,
            run_id=uuid.UUID(run_id),
            label=label,
            status="draft",
            published_at=None,
            profile=profile,
            metrics=metrics,
            recommended=recommended,
        )
    )
    session.flush()
    for sid, d, s in assignments:
        session.add(
            m.Assignment(
                id=uuid.uuid5(vid, f"{sid}/{d}/{s}"),
                variant_id=vid,
                staff_id=uuid.UUID(sid),
                date=d,
                shift_type=s,
            )
        )
    session.flush()
    return str(vid)


def _variant_info(v: m.RosterVariant) -> VariantInfo:
    return VariantInfo(
        str(v.id), v.label, v.status, v.profile, v.metrics, v.recommended, v.published_at
    )


def run(session: Session, run_id: str) -> Run | None:
    """Return a run with its variants."""
    r = session.get(m.RosterRun, uuid.UUID(run_id))
    if r is None:
        return None
    vs = session.scalars(
        select(m.RosterVariant)
        .where(m.RosterVariant.run_id == r.id)
        .order_by(m.RosterVariant.label)
    )
    return Run(
        str(r.id),
        r.roster_month,
        r.status,
        r.created_at,
        r.finished_at,
        r.rule_set_version,
        r.solver_version,
        r.validator_version,
        r.config,
        r.explanations,
        r.error,
        tuple(_variant_info(v) for v in vs),
    )


def runs_of(session: Session, month: date) -> list[Run]:
    """Return every run of a month, newest first."""
    ids = session.scalars(
        select(m.RosterRun.id)
        .where(m.RosterRun.roster_month == month)
        .order_by(m.RosterRun.created_at.desc())
    )
    return [r for i in ids if (r := run(session, str(i))) is not None]


def variant(session: Session, variant_id: str) -> tuple[VariantInfo, date] | None:
    """Return a variant and its roster month."""
    q = select(m.RosterVariant, m.RosterRun.roster_month).join(
        m.RosterRun, m.RosterRun.id == m.RosterVariant.run_id
    )
    row = session.execute(q.where(m.RosterVariant.id == uuid.UUID(variant_id))).first()
    return None if row is None else (_variant_info(row[0]), row[1])


def variant_assignments(session: Session, variant_id: str) -> list[Assignment]:
    """Return a variant's assignments (draft or published)."""
    info = variant(session, variant_id)
    if info is None:
        return []
    q = select(m.Assignment).where(m.Assignment.variant_id == uuid.UUID(variant_id))
    return [
        Assignment(str(a.id), str(a.staff_id), a.date, a.shift_type, info[1])
        for a in session.scalars(q)
    ]


def edit_draft(
    session: Session,
    variant_id: str,
    remove: list[tuple[str, date, str]],
    add: list[tuple[str, date, str]],
) -> None:
    """Change a draft variant directly (it is not visible to anyone yet)."""
    vid = uuid.UUID(variant_id)
    for sid, d, s in remove:
        a = session.scalar(
            select(m.Assignment).where(
                m.Assignment.variant_id == vid,
                m.Assignment.staff_id == uuid.UUID(sid),
                m.Assignment.date == d,
                m.Assignment.shift_type == s,
            )
        )
        if a is not None:
            session.delete(a)
    session.flush()
    for sid, d, s in add:
        session.add(
            m.Assignment(
                id=uuid.uuid5(vid, f"{sid}/{d}/{s}"),
                variant_id=vid,
                staff_id=uuid.UUID(sid),
                date=d,
                shift_type=s,
            )
        )
    session.flush()


def publish_variant(session: Session, variant_id: str, approved_by: str, now: datetime) -> None:
    """Publish a draft with the Planner's approval; the other drafts of the month are set aside."""
    info = variant(session, variant_id)
    if info is None:
        raise KeyError(variant_id)
    v, month = info
    if v.status != "draft":
        raise ValueError("only a draft can be published")
    if published(session, month) is not None:
        raise ValueError("this month is already published; change it with reasons instead")
    row = session.get(m.RosterVariant, uuid.UUID(variant_id))
    assert row is not None
    row.status, row.published_at = "published", now
    others = (
        select(m.RosterVariant)
        .join(m.RosterRun, m.RosterRun.id == m.RosterVariant.run_id)
        .where(
            m.RosterRun.roster_month == month,
            m.RosterVariant.status == "draft",
            m.RosterVariant.id != row.id,
        )
    )
    for o in session.scalars(others):
        o.status = "discarded"
    session.add(
        m.Approval(
            id=uuid.uuid5(row.id, "approval"),
            variant_id=row.id,
            approved_by=uuid.UUID(approved_by),
            approved_at=now,
            kind="planner",
        )
    )
    session.flush()


def record_change(
    session: Session,
    *,
    month: date,
    kind: str,
    assignment_id: str | None,
    day: date,
    shift_type: str,
    staff_before: str | None,
    staff_after: str | None,
    reason: str,
    changed_by: str,
    now: datetime,
) -> Change:
    """Record a change to a published roster."""
    c = m.AssignmentChange(
        id=uuid.uuid4(),  # random: two changes can happen at the same demo instant
        roster_month=month,
        kind=kind,
        assignment_id=None if assignment_id is None else uuid.UUID(assignment_id),
        date=day,
        shift_type=shift_type,
        staff_before=None if staff_before is None else uuid.UUID(staff_before),
        staff_after=None if staff_after is None else uuid.UUID(staff_after),
        reason=reason,
        changed_by=uuid.UUID(changed_by),
        changed_at=now,
    )
    session.add(c)
    session.flush()
    return _change(c)


def _change(c: m.AssignmentChange) -> Change:
    return Change(
        str(c.id),
        c.roster_month,
        c.kind,
        None if c.assignment_id is None else str(c.assignment_id),
        c.date,
        c.shift_type,
        None if c.staff_before is None else str(c.staff_before),
        None if c.staff_after is None else str(c.staff_after),
        c.reason,
        str(c.changed_by),
        c.changed_at,
    )


def changes(session: Session, start: date, end: date) -> list[Change]:
    """Return changes to published rosters on days from start to end, oldest first."""
    q = select(m.AssignmentChange).where(
        m.AssignmentChange.date >= start, m.AssignmentChange.date <= end
    )
    return [_change(c) for c in session.scalars(q.order_by(m.AssignmentChange.changed_at))]


def changes_for(session: Session, staff_id: str) -> list[Change]:
    """Return changes that concern a physician (before or after), newest first."""
    sid = uuid.UUID(staff_id)
    q = select(m.AssignmentChange).where(
        (m.AssignmentChange.staff_before == sid) | (m.AssignmentChange.staff_after == sid)
    )
    return [_change(c) for c in session.scalars(q.order_by(m.AssignmentChange.changed_at.desc()))]
