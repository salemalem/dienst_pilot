"""Public interface of the audit context: record and read events. No update, no delete."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from dienstpilot.audit import chain
from dienstpilot.audit.models import ChainCheck, ChainHead, Event


@dataclass(frozen=True)
class EventView:
    """An audit event as stored (the API layer applies privacy rules before showing it)."""

    id: str
    occurred_at: datetime
    actor_label: str
    action: str
    subject_type: str
    subject_id: str | None
    staff_id: str | None
    payload: dict[str, Any]
    seq: int = 0
    hash: str = ""
    prev_hash: str = ""


def _lock_head(session: Session, key: str) -> ChainHead:
    """Return the chain's head row, locked until the transaction ends (created on first use)."""
    session.execute(
        pg_insert(ChainHead)
        .values(chain_key=key, head_seq=0, head_hash=chain.GENESIS)
        .on_conflict_do_nothing(index_elements=["chain_key"])
    )
    head = session.scalars(
        select(ChainHead)
        .where(ChainHead.chain_key == key)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    return head


def record(
    session: Session,
    *,
    occurred_at: datetime,
    department_id: str | None,
    actor_user_id: str | None,
    actor_label: str,
    action: str,
    subject_type: str,
    subject_id: str | None = None,
    staff_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Append one event to its hash chain and return its id.

    ``department_id`` None puts the event on the system chain. The chain head is locked until
    the transaction ends, so concurrent writers queue up and ``seq`` has no gaps.
    """
    # Random ids: the demo clock can stand still, and two changes of the same subject at the same
    # instant (for example the policy switched twice) are two events. Order is ``seq``.
    event_id = uuid.uuid4()
    key = chain.chain_key(department_id)
    head = _lock_head(session, key)
    seq = head.head_seq + 1
    body = chain.normalise_payload(payload)
    digest = chain.link(
        head.head_hash,
        chain.canonical(
            chain=key,
            seq=seq,
            event_id=event_id,
            occurred_at=occurred_at,
            department_id=department_id,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            staff_id=staff_id,
            payload=body,
        ),
    )
    session.add(
        Event(
            id=event_id,
            occurred_at=occurred_at,
            department_id=None if department_id is None else uuid.UUID(department_id),
            chain_key=key,
            seq=seq,
            prev_hash=head.head_hash,
            hash=digest,
            actor_user_id=None if actor_user_id is None else uuid.UUID(actor_user_id),
            actor_label=actor_label,
            action=action,
            subject_type=subject_type,
            subject_id=None if subject_id is None else uuid.UUID(subject_id),
            staff_id=None if staff_id is None else uuid.UUID(staff_id),
            payload=body,
        )
    )
    head.head_seq, head.head_hash = seq, digest
    session.flush()
    return str(event_id)


def _query(
    department_id: str,
    action_prefix: str | None,
    staff_id: str | None,
    since: datetime | None,
    until: datetime | None,
) -> Select[Event]:
    q = select(Event).where(Event.chain_key == department_id)
    if action_prefix:
        q = q.where(Event.action.startswith(action_prefix))
    if staff_id:
        q = q.where(Event.staff_id == uuid.UUID(staff_id))
    if since:
        q = q.where(Event.occurred_at >= since)
    if until:
        q = q.where(Event.occurred_at <= until)
    return q


def list_events(
    session: Session,
    department_id: str,
    *,
    action_prefix: str | None = None,
    staff_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[EventView]]:
    """Return (total, page) of events, newest first."""
    q = _query(department_id, action_prefix, staff_id, since, until)
    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = session.scalars(q.order_by(Event.seq.desc()).limit(limit).offset(offset))
    return total, [
        EventView(
            str(e.id),
            e.occurred_at,
            e.actor_label,
            e.action,
            e.subject_type,
            None if e.subject_id is None else str(e.subject_id),
            None if e.staff_id is None else str(e.staff_id),
            dict(e.payload),
            e.seq,
            e.hash,
            e.prev_hash,
        )
        for e in rows
    ]


# --- verification -----------------------------------------------------------------------------

STALE_AFTER = timedelta(hours=36)  # a check older than this (in demo time) no longer counts


@dataclass(frozen=True)
class ChainResult:
    """What the verifier found in one chain."""

    chain_key: str
    ok: bool
    rows: int
    head_seq: int
    head_hash: str
    first_bad_seq: int | None = None
    reason: str | None = None


def _row_fields(e: Event) -> bytes:
    return chain.canonical(
        chain=e.chain_key,
        seq=e.seq,
        event_id=e.id,
        occurred_at=e.occurred_at,
        department_id=e.department_id,
        actor_user_id=e.actor_user_id,
        actor_label=e.actor_label,
        action=e.action,
        subject_type=e.subject_type,
        subject_id=e.subject_id,
        staff_id=e.staff_id,
        payload=e.payload,
    )


def _walk(
    session: Session, key: str, after_seq: int, after_hash: str
) -> tuple[int, int, str, int | None, str | None]:
    """Check the rows after ``after_seq``; return (rows, last_seq, last_hash, bad_seq, reason)."""
    seq, prev, rows = after_seq, after_hash, 0
    q = (
        select(Event)
        .where(Event.chain_key == key, Event.seq > after_seq)
        .order_by(Event.seq)
        .execution_options(yield_per=2000)
    )
    for e in session.scalars(q):
        expected = seq + 1
        if e.seq != expected:
            return rows, seq, prev, expected, "gap in the sequence (an entry is missing)"
        if e.prev_hash != prev:
            return rows, seq, prev, e.seq, "link to the previous entry is broken"
        if chain.link(prev, _row_fields(e)) != e.hash:
            return rows, seq, prev, e.seq, "entry content does not match its hash"
        seq, prev, rows = e.seq, e.hash, rows + 1
    return rows, seq, prev, None, None


def verify_chain(session: Session, key: str) -> ChainResult:
    """Recompute a whole chain from the first entry and compare it with the stored head."""
    rows, seq, last, bad, reason = _walk(session, key, 0, chain.GENESIS)
    if bad is None:
        head = session.get(ChainHead, key)
        if head is None and rows:
            bad, reason = seq + 1, "chain head missing"
        elif head is not None and (head.head_seq, head.head_hash) != (seq, last):
            bad, reason = seq + 1, "entries after the last verified one are missing"
    return ChainResult(key, bad is None, rows, seq, last, bad, reason)


def run_check(
    session: Session, department_id: str, now: datetime, trigger: str
) -> list[ChainResult]:
    """Verify the department's chain and the system chain; store one check per chain."""
    results = []
    for key in (department_id, chain.SYSTEM_CHAIN):
        res = verify_chain(session, key)
        if key == chain.SYSTEM_CHAIN and res.rows == 0 and res.ok:
            continue
        session.add(
            ChainCheck(
                chain_key=key,
                checked_at=now,
                trigger=trigger,
                ok=res.ok,
                rows=res.rows,
                head_seq=res.head_seq,
                head_hash=res.head_hash,
                first_bad_seq=res.first_bad_seq,
                reason=res.reason,
            )
        )
        results.append(res)
    session.flush()
    return results


@dataclass(frozen=True)
class ChainStatus:
    """What W10 may say about the log: verified, stale, failed or never checked."""

    state: str  # verified | stale | failed | never_checked
    checked_at: datetime | None = None
    trigger: str | None = None
    rows: int = 0
    head_hash: str | None = None
    newer_events: int = 0
    first_bad_seq: int | None = None
    reason: str | None = None


def chain_status(session: Session, department_id: str, now: datetime) -> ChainStatus:
    """Combine the latest stored checks with a cheap look at what was appended since.

    "verified" needs: the last full check passed, it is not older than 36 hours of demo time,
    and every entry appended after it links correctly to the verified head. Changes to older
    entries are found by the next check (nightly, or on demand).
    """
    checks = []
    newer_system = 0
    for key in (department_id, chain.SYSTEM_CHAIN):
        last = session.scalars(
            select(ChainCheck)
            .where(ChainCheck.chain_key == key)
            .order_by(ChainCheck.id.desc())
            .limit(1)
        ).first()
        head = session.get(ChainHead, key)
        if last is None:
            if key == department_id:
                return ChainStatus("never_checked")
            if head is not None and head.head_seq > 0:
                # The system chain (clock changes) started after the last check: its few
                # entries are verified from the start on every read.
                n, _, _, bad, reason = _walk(session, key, 0, chain.GENESIS)
                if bad is not None:
                    return ChainStatus("failed", None, None, 0, None, n, bad, reason)
                newer_system += n
            continue
        checks.append(last)
    first = checks[0]
    rows = sum(c.rows for c in checks)
    newer = 0
    for c in checks:
        if not c.ok:
            return ChainStatus(
                "failed", c.checked_at, c.trigger, rows, c.head_hash, 0, c.first_bad_seq, c.reason
            )
        n, _, _, bad, reason = _walk(session, c.chain_key, c.head_seq, c.head_hash)
        head = session.get(ChainHead, c.chain_key)
        if bad is None and head is not None and head.head_seq < c.head_seq:
            bad, reason = c.head_seq, "entries were removed since the last check"
        if bad is not None:
            return ChainStatus("failed", c.checked_at, c.trigger, rows, c.head_hash, n, bad, reason)
        newer += n
    newer += newer_system
    oldest = min(c.checked_at for c in checks)
    state = "stale" if now - oldest > STALE_AFTER else "verified"
    return ChainStatus(state, oldest, first.trigger, rows, first.head_hash, newer)


def head(session: Session, department_id: str) -> tuple[int, str]:
    """Return (seq, hash) of the newest entry of the department's chain, (0, genesis) if empty."""
    h = session.get(ChainHead, department_id)
    return (0, chain.GENESIS) if h is None else (h.head_seq, h.head_hash)


def trail(
    session: Session, department_id: str, since: datetime, until: datetime
) -> list[EventView]:
    """Return the department's events in [since, until], oldest first (by sequence)."""
    out: list[EventView] = []
    offset = 0
    while True:
        _, page = list_events(
            session, department_id, since=since, until=until, limit=500, offset=offset
        )
        out += page
        if len(page) < 500:
            break
        offset += 500
    out.reverse()
    return out


def departments(session: Session) -> list[str]:
    """Return the departments that have an audit chain (not the system chain)."""
    return list(
        session.scalars(
            select(ChainHead.chain_key)
            .where(ChainHead.chain_key != chain.SYSTEM_CHAIN)
            .order_by(ChainHead.chain_key)
        )
    )
