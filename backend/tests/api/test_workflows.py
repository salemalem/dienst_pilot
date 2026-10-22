"""Durable workflows on the demo clock: timers, ordering, the cascade, exactly-once (ADR-017)."""

import random
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from dienstpilot.shared.clock import FixedClock
from dienstpilot.shared.settings import DEMO_NOW
from dienstpilot.shared.workflows import engine, machines
from dienstpilot.shared.workflows.models import Timer

from .test_flows import _report_sick

pytestmark = pytest.mark.db


@pytest.fixture
def db(app_factory: Any) -> Any:
    with Session(bind=app_factory.conn, join_transaction_mode="create_savepoint") as s:
        yield s


def _env(now: datetime) -> engine.Env:
    return engine.Env(FixedClock(now))


@pytest.fixture
def fired(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, datetime]]:
    log: list[tuple[str, datetime]] = []
    monkeypatch.setitem(engine.HANDLERS, "test.tick", lambda s, t, e: log.append((t.key, t.due_at)))
    return log


# --- the timer rules ---------------------------------------------------------------------------


def test_a_clock_jump_fires_every_due_timer_in_order_and_none_early(
    db: Session, fired: list[tuple[str, datetime]]
) -> None:
    rng = random.Random(7)
    base = DEMO_NOW + timedelta(days=400)  # clear of the seeded timers
    due = {f"k{i}": base + timedelta(minutes=rng.randrange(0, 6000)) for i in range(60)}
    for k in rng.sample(sorted(due), len(due)):  # armed in a different order than due
        assert engine.arm(db, "test.tick", k, due[k])
    cut = base + timedelta(minutes=3000)
    engine.fire_due(db, _env(cut), cut)
    expect = sorted((v, k) for k, v in due.items() if v <= cut)
    assert [(d, k) for k, d in fired] == expect
    assert all(d <= cut for _, d in fired)
    assert engine.fire_due(db, _env(cut), cut) == []  # nothing fires twice
    later = base + timedelta(days=30)
    engine.fire_due(db, _env(later), later)
    assert len(fired) == 60 and [d for _, d in fired] == sorted(due.values())


def test_arming_the_same_timer_twice_is_a_no_op(db: Session) -> None:
    t = DEMO_NOW + timedelta(days=500)
    assert engine.arm(db, "test.tick", "same", t)
    assert not engine.arm(db, "test.tick", "same", t + timedelta(days=1))
    assert db.scalar(select(func.count()).select_from(Timer).where(Timer.key == "same")) == 1


def test_a_cancelled_timer_never_fires(db: Session, fired: list[tuple[str, datetime]]) -> None:
    t = DEMO_NOW + timedelta(days=500)
    engine.arm(db, "test.tick", "gone", t)
    engine.cancel(db, "test.tick", "gone", DEMO_NOW)
    engine.fire_due(db, _env(t + timedelta(days=1)), t + timedelta(days=1))
    assert fired == []


def test_a_timer_that_keeps_failing_is_set_aside_after_three_attempts(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def boom(s: Session, t: engine.TimerView, e: engine.Env) -> None:
        calls.append(t.key)
        raise RuntimeError("no")

    monkeypatch.setitem(engine.HANDLERS, "test.boom", boom)
    t = DEMO_NOW + timedelta(days=600)
    engine.arm(db, "test.boom", "x", t)
    for _ in range(5):
        engine.fire_due(db, _env(t), t)
    assert len(calls) == 3
    row = db.scalars(select(Timer).where(Timer.key == "x")).one()
    assert row.failed_at is not None and row.fired_at is None and "no" in (row.last_error or "")


def test_the_state_machine_refuses_a_skipped_state(db: Session) -> None:
    engine.start(db, machines.SICK_CASCADE, "k-skip", DEMO_NOW)
    with pytest.raises(engine.IllegalTransitionError):
        engine.move(db, machines.SICK_CASCADE, "k-skip", "filled", DEMO_NOW)
    engine.move(db, machines.SICK_CASCADE, "k-skip", "asking", DEMO_NOW)
    engine.move(db, machines.SICK_CASCADE, "k-skip", "filled", DEMO_NOW)
    assert engine.state_of(db, machines.SICK_CASCADE, "k-skip") == "filled"


# --- the sick-call cascade ---------------------------------------------------------------------


def _offers(conn: Any, cascade_id: str) -> list[tuple[str, str, datetime, datetime]]:
    rows = conn.execute(
        text(
            "SELECT staff_id::text, response, asked_at, deadline_at FROM operations.cover_offer"
            " WHERE cascade_id = :c ORDER BY rank"
        ),
        {"c": cascade_id},
    ).all()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def test_the_cascade_moves_on_at_each_deadline_even_after_a_long_jump(
    client: Any, login: Any, clock: Any, app_factory: Any
) -> None:
    _, cascade = _report_sick(client, login)
    cid = cascade["id"]
    conn = app_factory.conn
    assert engine.state_of(Session(bind=conn), machines.SICK_CASCADE, cid) == "asking"
    timers = conn.execute(
        text(
            "SELECT count(*) FROM workflow.timer WHERE kind = 'cover.timeout' AND fired_at IS NULL"
        )
    ).scalar_one()
    assert timers >= 1
    # Nobody answers for two hours: every colleague is asked in turn, 15 minutes apart.
    clock.value = DEMO_NOW + timedelta(hours=2)
    detail = client.get(f"/planner/cascades/{cid}", headers=login("brandt")).json()["cascade"]
    offers = _offers(conn, cid)
    assert len(offers) == len({o[0] for o in offers}), "nobody was asked twice"
    assert all(o[1] == "no_response" for o in offers)
    for a, b in pairwise(offers):
        assert b[2] == a[3] and b[3] - b[2] == timedelta(minutes=15)  # asked when the last expired
    assert (
        detail["status"] == "pending_approval" and detail["escalation_reason"] == "list_exhausted"
    )
    assert engine.state_of(Session(bind=conn), machines.SICK_CASCADE, cid) == "escalated"
    assert (
        conn.execute(
            text(
                "SELECT count(*) FROM workflow.timer WHERE kind='cover.timeout' AND key IN"
                " (SELECT id::text FROM operations.cover_offer WHERE cascade_id = :c)"
                " AND fired_at IS NULL AND cancelled_at IS NULL"
            ),
            {"c": cid},
        ).scalar_one()
        == 0
    )
    # The escalation reached the event stream.
    assert (
        conn.execute(
            text(
                "SELECT count(*) FROM events.outbox WHERE event_type = 'CoverEscalated'"
                " AND payload->>'cascade_id' = :c"
            ),
            {"c": cid},
        ).scalar_one()
        == 1
    )


def test_an_answer_cancels_the_deadline_timer(
    client: Any, login: Any, clock: Any, app_factory: Any, as_staff: Any
) -> None:
    shift, cascade = _report_sick(client, login)
    conn = app_factory.conn
    first = _offers(conn, cascade["id"])[0][0]
    h = as_staff(first)
    offer = next(
        o
        for o in client.get("/me/cover-requests", headers=h).json()
        if o["shift"]["date"] == shift["date"]
    )
    assert (
        client.post(
            f"/me/cover-requests/{offer['offer_id']}", json={"accept": False}, headers=h
        ).status_code
        == 200
    )
    cancelled = conn.execute(
        text("SELECT cancelled_at IS NOT NULL FROM workflow.timer WHERE key = :k"),
        {"k": offer["offer_id"]},
    ).scalar_one()
    assert cancelled
    clock.value = DEMO_NOW + timedelta(minutes=16)
    client.get("/planner/cascades", headers=login("brandt"))
    first_row = _offers(conn, cascade["id"])[0]
    assert first_row[1] == "declined"  # the deadline did not overwrite the answer


def test_swap_workflow_follows_its_machine(client: Any, login: Any, app_factory: Any) -> None:
    from .helpers import coverable_shift

    weber = login("weber")
    s = coverable_shift(client, weber)
    sw = client.post("/me/swaps", json={"assignment_id": s["assignment_id"]}, headers=weber).json()
    inst = Session(bind=app_factory.conn)
    assert engine.state_of(inst, machines.SWAP_APPROVAL, sw["id"]) == "offered"
