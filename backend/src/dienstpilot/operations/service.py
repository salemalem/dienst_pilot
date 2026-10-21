"""Public interface of the operations context: absences, swaps and cover cascades.

Phase 3A: there is no validator (C2) yet, so a taken swap or an accepted cover waits for the
Planner instead of being approved automatically (escalation reason "validator_unavailable").
Cascades advance lazily: a request older than its 15-minute deadline moves on when read.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from dienstpilot.operations import models as m

ANSWER_WINDOW = timedelta(minutes=15)
VALIDATOR_UNAVAILABLE = "validator_unavailable"
LIST_EXHAUSTED = "list_exhausted"


@dataclass(frozen=True)
class Absence:
    """An absence. The category is for the Planner only; the API layer hides it from others."""

    id: str
    staff_id: str
    start_date: date
    end_date: date
    category: str
    reported_at: datetime


@dataclass(frozen=True)
class Swap:
    """A swap offer and where it stands."""

    id: str
    assignment_id: str
    offered_by: str
    offered_at: datetime
    accepted_by: str | None
    accepted_at: datetime | None
    status: str
    approval: str | None
    escalation_reason: str | None
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str | None


@dataclass(frozen=True)
class CoverOffer:
    """One colleague asked in a cascade."""

    id: str
    staff_id: str
    rank: int
    asked_at: datetime
    deadline_at: datetime | None
    responded_at: datetime | None
    response: str


@dataclass(frozen=True)
class Cascade:
    """A cover search after a sick report."""

    id: str
    assignment_id: str
    absence_id: str
    opened_at: datetime
    closed_at: datetime | None
    status: str
    outcome: str | None
    covered_by: str | None
    escalation_reason: str | None
    queue: tuple[str, ...]
    offers: tuple[CoverOffer, ...]


@dataclass(frozen=True)
class HolderChange:
    """A published assignment changed hands (or lost its holder) at ``at``."""

    at: datetime
    assignment_id: str
    holder: str | None  # None: nobody of the department holds it
    note: str  # swap | cover | locum | unfilled | open


def _uid(*parts: object) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "/".join(str(p) for p in parts))


def _s(v: uuid.UUID | None) -> str | None:
    return None if v is None else str(v)


# --- absences --------------------------------------------------------------------------------


def absences(session: Session, staff_ids: list[str], start: date, end: date) -> list[Absence]:
    """Return absences of the given people overlapping start..end."""
    q = select(m.Absence).where(
        m.Absence.staff_id.in_([uuid.UUID(s) for s in staff_ids]),
        m.Absence.end_date >= start,
        m.Absence.start_date <= end,
    )
    return [
        Absence(str(a.id), str(a.staff_id), a.start_date, a.end_date, a.category, a.reported_at)
        for a in session.scalars(q.order_by(m.Absence.start_date))
    ]


def report_absence(
    session: Session, staff_id: str, start: date, end: date, now: datetime
) -> Absence:
    """Record a sick report (status and dates only; there is no diagnosis field)."""
    a = m.Absence(
        id=_uid("absence", staff_id, start, now.isoformat()),
        staff_id=uuid.UUID(staff_id),
        start_date=start,
        end_date=end,
        category="sick",
        reported_at=now,
    )
    session.add(a)
    session.flush()
    return Absence(str(a.id), staff_id, start, end, "sick", now)


# --- swaps -----------------------------------------------------------------------------------


def _swap(s: m.SwapOffer) -> Swap:
    return Swap(
        str(s.id),
        str(s.assignment_id),
        str(s.offered_by),
        s.offered_at,
        _s(s.accepted_by),
        s.accepted_at,
        s.status,
        s.approval,
        s.escalation_reason,
        _s(s.decided_by),
        s.decided_at,
        s.decision_reason,
    )


def swaps(
    session: Session,
    *,
    statuses: list[str] | None = None,
    staff_id: str | None = None,
    since: datetime | None = None,
) -> list[Swap]:
    """Return swap offers, newest first."""
    q = select(m.SwapOffer)
    if statuses:
        q = q.where(m.SwapOffer.status.in_(statuses))
    if staff_id:
        sid = uuid.UUID(staff_id)
        q = q.where((m.SwapOffer.offered_by == sid) | (m.SwapOffer.accepted_by == sid))
    if since:
        q = q.where(m.SwapOffer.offered_at >= since)
    return [_swap(s) for s in session.scalars(q.order_by(m.SwapOffer.offered_at.desc()))]


def swap(session: Session, swap_id: str) -> Swap | None:
    """Return one swap offer."""
    s = session.get(m.SwapOffer, uuid.UUID(swap_id))
    return None if s is None else _swap(s)


def offer_swap(session: Session, assignment_id: str, offered_by: str, now: datetime) -> Swap:
    """Offer a shift to eligible colleagues."""
    s = m.SwapOffer(
        id=_uid("swap", assignment_id, offered_by, now.isoformat()),
        assignment_id=uuid.UUID(assignment_id),
        offered_by=uuid.UUID(offered_by),
        offered_at=now,
        status="open",
    )
    session.add(s)
    session.flush()
    return _swap(s)


def take_swap(session: Session, swap_id: str, taker: str, now: datetime) -> Swap:
    """Record that a colleague takes an offer; without the validator it waits for the Planner."""
    s = session.get(m.SwapOffer, uuid.UUID(swap_id))
    if s is None:
        raise KeyError(swap_id)
    if s.status != "open":
        raise ValueError("offer is not open")
    s.accepted_by, s.accepted_at = uuid.UUID(taker), now
    s.status, s.escalation_reason = "pending_approval", VALIDATOR_UNAVAILABLE
    session.flush()
    return _swap(s)


def decide_swap(
    session: Session, swap_id: str, approve: bool, by: str, reason: str | None, now: datetime
) -> Swap:
    """Record the Planner approving or declining a taken swap."""
    s = session.get(m.SwapOffer, uuid.UUID(swap_id))
    if s is None:
        raise KeyError(swap_id)
    if s.status != "pending_approval":
        raise ValueError("swap is not waiting for a decision")
    s.status = "approved" if approve else "declined"
    s.approval, s.decided_by, s.decided_at = "planner", uuid.UUID(by), now
    s.decision_reason = None if approve else reason
    session.flush()
    return _swap(s)


# --- cover cascades --------------------------------------------------------------------------


def _offer(o: m.CoverOffer) -> CoverOffer:
    return CoverOffer(
        str(o.id), str(o.staff_id), o.rank, o.asked_at, o.deadline_at, o.responded_at, o.response
    )


def _cascade(session: Session, c: m.CoverCascade) -> Cascade:
    offers = session.scalars(
        select(m.CoverOffer).where(m.CoverOffer.cascade_id == c.id).order_by(m.CoverOffer.rank)
    )
    return Cascade(
        str(c.id),
        str(c.assignment_id),
        str(c.absence_id),
        c.opened_at,
        c.closed_at,
        c.status,
        c.outcome,
        _s(c.covered_by),
        c.escalation_reason,
        tuple(c.candidate_queue or ()),
        tuple(_offer(o) for o in offers),
    )


def _ask(session: Session, c: m.CoverCascade, at: datetime) -> None:
    """Ask the next colleague in the queue, or hand the cascade to the Planner if none is left."""
    queue = list(c.candidate_queue or [])
    if not queue:
        c.status, c.escalation_reason = "pending_approval", LIST_EXHAUSTED
        return
    nxt, rest = queue[0], queue[1:]
    rank = 1 + len(
        list(session.scalars(select(m.CoverOffer.id).where(m.CoverOffer.cascade_id == c.id)))
    )
    session.add(
        m.CoverOffer(
            id=_uid("cover-offer", c.id, rank),
            cascade_id=c.id,
            staff_id=uuid.UUID(nxt),
            rank=rank,
            asked_at=at,
            deadline_at=at + ANSWER_WINDOW,
            response="pending",
        )
    )
    c.candidate_queue = rest


def open_cascade(
    session: Session,
    assignment_id: str,
    absence_id: str,
    ranked_candidates: list[str],
    now: datetime,
) -> Cascade:
    """Start a cover search with colleagues in the order the ranking chose."""
    c = m.CoverCascade(
        id=_uid("cascade", assignment_id, absence_id),
        assignment_id=uuid.UUID(assignment_id),
        absence_id=uuid.UUID(absence_id),
        opened_at=now,
        status="open",
        candidate_queue=list(ranked_candidates),
    )
    session.add(c)
    session.flush()
    _ask(session, c, now)
    session.flush()
    return _cascade(session, c)


def advance(session: Session, now: datetime) -> list[tuple[str, str]]:
    """Move every open cascade past expired requests. Returns (cascade id, staff id) timed out."""
    timed_out = []
    for c in session.scalars(select(m.CoverCascade).where(m.CoverCascade.status == "open")):
        while True:
            pending = session.scalar(
                select(m.CoverOffer).where(
                    m.CoverOffer.cascade_id == c.id, m.CoverOffer.response == "pending"
                )
            )
            if pending is None or pending.deadline_at is None or pending.deadline_at > now:
                break
            pending.response = "no_response"
            timed_out.append((str(c.id), str(pending.staff_id)))
            _ask(session, c, pending.deadline_at)
            session.flush()
            if c.status != "open":
                break
    session.flush()
    return timed_out


def respond(session: Session, offer_id: str, staff_id: str, accept: bool, now: datetime) -> Cascade:
    """Record a colleague's answer to a cover request; acceptance waits for the Planner."""
    o = session.get(m.CoverOffer, uuid.UUID(offer_id))
    if o is None or str(o.staff_id) != staff_id:
        raise KeyError(offer_id)
    if o.response != "pending" or (o.deadline_at is not None and o.deadline_at <= now):
        raise ValueError("this request is no longer open")
    c = session.get(m.CoverCascade, o.cascade_id)
    assert c is not None
    o.response, o.responded_at = ("accepted" if accept else "declined"), now
    if accept:
        c.covered_by, c.status, c.escalation_reason = (
            o.staff_id,
            "pending_approval",
            VALIDATOR_UNAVAILABLE,
        )
    else:
        _ask(session, c, now)
    session.flush()
    return _cascade(session, c)


def decide_cascade(
    session: Session, cascade_id: str, outcome: str, covered_by: str | None, now: datetime
) -> Cascade:
    """Close a cascade as the Planner decides: confirm, assign (overtime), locum or unfilled."""
    c = session.get(m.CoverCascade, uuid.UUID(cascade_id))
    if c is None:
        raise KeyError(cascade_id)
    if c.status != "pending_approval":
        raise ValueError("cascade is not waiting for a decision")
    if outcome not in ("covered", "escalated_overtime", "locum", "unfilled"):
        raise ValueError(outcome)
    c.outcome, c.status, c.closed_at = outcome, "closed", now
    c.covered_by = (
        uuid.UUID(covered_by) if covered_by else (c.covered_by if outcome == "covered" else None)
    )
    session.flush()
    return _cascade(session, c)


def cascades(
    session: Session,
    *,
    statuses: list[str] | None = None,
    since: datetime | None = None,
    assignment_ids: list[str] | None = None,
) -> list[Cascade]:
    """Return cascades, newest first."""
    q = select(m.CoverCascade)
    if statuses:
        q = q.where(m.CoverCascade.status.in_(statuses))
    if since:
        q = q.where(m.CoverCascade.opened_at >= since)
    if assignment_ids is not None:
        q = q.where(m.CoverCascade.assignment_id.in_([uuid.UUID(a) for a in assignment_ids]))
    return [
        _cascade(session, c) for c in session.scalars(q.order_by(m.CoverCascade.opened_at.desc()))
    ]


def cascade(session: Session, cascade_id: str) -> Cascade | None:
    """Return one cascade."""
    c = session.get(m.CoverCascade, uuid.UUID(cascade_id))
    return None if c is None else _cascade(session, c)


def pending_offers_for(session: Session, staff_id: str) -> list[tuple[CoverOffer, str]]:
    """Return (offer, assignment id) of open cover requests to a person."""
    q = (
        select(m.CoverOffer, m.CoverCascade.assignment_id)
        .join(m.CoverCascade, m.CoverCascade.id == m.CoverOffer.cascade_id)
        .where(m.CoverOffer.staff_id == uuid.UUID(staff_id), m.CoverOffer.response == "pending")
    )
    return [(_offer(o), str(a)) for o, a in session.execute(q)]


def holder_changes(session: Session, assignment_ids: list[str]) -> list[HolderChange]:
    """Return changes of holder for the given published assignments, in time order."""
    ids = [uuid.UUID(a) for a in assignment_ids]
    out: list[HolderChange] = []
    for s in session.scalars(select(m.SwapOffer).where(m.SwapOffer.assignment_id.in_(ids))):
        if s.status in ("accepted", "approved") and s.accepted_by is not None:
            at = s.decided_at or s.accepted_at or s.offered_at
            out.append(HolderChange(at, str(s.assignment_id), str(s.accepted_by), "swap"))
    for c in session.scalars(select(m.CoverCascade).where(m.CoverCascade.assignment_id.in_(ids))):
        if c.status != "closed":
            out.append(HolderChange(c.opened_at, str(c.assignment_id), None, "open"))
        elif c.covered_by is not None:
            out.append(HolderChange(c.opened_at, str(c.assignment_id), str(c.covered_by), "cover"))
        else:
            out.append(
                HolderChange(c.opened_at, str(c.assignment_id), None, c.outcome or "unfilled")
            )
    return sorted(out, key=lambda h: (h.at, h.assignment_id))
