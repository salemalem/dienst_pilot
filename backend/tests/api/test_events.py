"""Outbox, relay and idempotent consumers (ADR-016)."""

import uuid
from datetime import timedelta
from typing import Any

import jsonschema
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from dienstpilot import recording
from dienstpilot.shared.events import outbox
from dienstpilot.shared.events.consumer import Consumer, Event, consume
from dienstpilot.shared.events.models import Outbox, Processed
from dienstpilot.shared.events.relay import relay
from dienstpilot.shared.events.stream import MemoryStream
from dienstpilot.shared.settings import DEMO_NOW

pytestmark = pytest.mark.db
U = "0fa0e226-bbae-5a54-b05a-db82a17ca3d0"


@pytest.fixture
def db(app_factory: Any) -> Any:
    with Session(bind=app_factory.conn, join_transaction_mode="create_savepoint") as s:
        s.execute(text("DELETE FROM events.outbox"))
        yield s


def _publish(db: Session, n: int = 1) -> list[str]:
    return [
        outbox.publish(
            db,
            "WindowClosed",
            {"window_id": str(uuid.uuid4())},
            occurred_at=DEMO_NOW + timedelta(minutes=i),
            department_id=U,
        )
        for i in range(n)
    ]


def test_publish_validates_and_writes_in_the_callers_transaction(db: Session) -> None:
    with pytest.raises(jsonschema.ValidationError):
        outbox.publish(
            db, "WindowClosed", {"window_id": "x"}, occurred_at=DEMO_NOW, department_id=U
        )
    ids = _publish(db, 2)
    assert db.scalar(select(func.count()).select_from(Outbox)) == 2
    db.rollback()  # the state change is rolled back: the event goes with it
    assert db.scalar(select(func.count()).select_from(Outbox)) == 0
    assert ids


def test_relay_sends_oldest_first_once(db: Session) -> None:
    ids = _publish(db, 3)
    stream = MemoryStream()
    assert relay(db, stream, DEMO_NOW) == 3
    assert [m.fields["event_id"] for m in stream.entries] == ids
    assert relay(db, stream, DEMO_NOW) == 0  # nothing new
    assert len(stream.entries) == 3


def test_consumer_handles_each_event_once_even_if_it_is_delivered_twice(db: Session) -> None:
    ids = _publish(db, 2)
    stream = MemoryStream()
    relay(db, stream, DEMO_NOW)
    seen: list[str] = []
    c = Consumer("c1", {"WindowClosed": lambda s, e: seen.append(e.event_id)})
    assert consume(db, stream, c, DEMO_NOW) == 2
    # The relay crashed after XADD and before the commit: the same rows are sent again.
    db.execute(text("UPDATE events.outbox SET relayed_at = NULL"))
    relay(db, stream, DEMO_NOW)
    assert len(stream.entries) == 4
    assert consume(db, stream, c, DEMO_NOW) == 0  # deduplicated on event_id
    assert seen == ids


def test_dedup_is_per_consumer(db: Session) -> None:
    _publish(db)
    stream = MemoryStream()
    relay(db, stream, DEMO_NOW)
    a: list[str] = []
    b: list[str] = []
    ca = Consumer("a", {"WindowClosed": lambda s, e: a.append(e.event_id)})
    cb = Consumer("b", {"WindowClosed": lambda s, e: b.append(e.event_id)})
    consume(db, stream, ca, DEMO_NOW)
    consume(db, stream, cb, DEMO_NOW)
    assert len(a) == len(b) == 1
    assert db.scalar(select(func.count()).select_from(Processed)) >= 2


def test_a_crash_after_commit_before_ack_does_not_run_the_handler_again(db: Session) -> None:
    _publish(db)
    stream = MemoryStream()
    relay(db, stream, DEMO_NOW)
    runs: list[str] = []
    c = Consumer("c", {"WindowClosed": lambda s, e: runs.append(e.event_id)})
    real_ack = stream.ack
    stream.ack = lambda g, m: None  # type: ignore[method-assign]  # the process dies here
    assert consume(db, stream, c, DEMO_NOW) == 1
    stream.ack = real_ack  # type: ignore[method-assign]
    assert consume(db, stream, c, DEMO_NOW) == 0  # redelivered, skipped, acknowledged
    assert len(runs) == 1 and not stream._pending["c"]


def test_a_failing_handler_leaves_the_event_pending_and_retries(db: Session) -> None:
    _publish(db)
    stream = MemoryStream()
    relay(db, stream, DEMO_NOW)
    calls = {"n": 0}

    def flaky(s: Session, e: Event) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")

    c = Consumer("c", {"WindowClosed": flaky})
    assert consume(db, stream, c, DEMO_NOW) == 0
    assert (
        db.scalar(select(func.count()).select_from(Processed).where(Processed.consumer == "c")) == 0
    )
    assert consume(db, stream, c, DEMO_NOW) == 1 and calls["n"] == 2


def test_audit_and_event_are_written_together_and_carry_no_category(db: Session) -> None:
    recording.record(
        db,
        occurred_at=DEMO_NOW,
        department_id=U,
        actor_user_id=None,
        actor_label="Dr. Test",
        action="absence.reported",
        subject_type="absence",
        subject_id=U,
        staff_id=U,
        payload={"start_date": "2026-10-20", "end_date": "2026-10-20", "category": "sick"},
    )
    row = db.scalars(select(Outbox).where(Outbox.event_type == "SicknessReported")).one()
    assert "category" not in row.payload and set(row.payload) == {
        "absence_id",
        "staff_id",
        "start_date",
        "end_date",
    }


def test_the_api_publishes_what_it_audits(client: Any, login: Any, app_factory: Any) -> None:
    app_factory.conn.execute(text("DELETE FROM events.outbox"))
    h = login("weber")
    r = client.post(
        "/me/sick", json={"start_date": "2026-10-20", "end_date": "2026-10-20"}, headers=h
    )
    assert r.status_code == 201
    types = [
        t
        for (t,) in app_factory.conn.execute(
            text("SELECT event_type FROM events.outbox ORDER BY seq")
        )
    ]
    assert types[0] == "SicknessReported" and "CoverRequested" in types


def test_redis_streams_end_to_end(db: Session) -> None:
    import os

    import redis as redis_lib

    from dienstpilot.shared.events.stream import RedisStream

    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL not set")
    r = redis_lib.Redis.from_url(url)
    name = f"dienstpilot:test:{uuid.uuid4()}"
    stream = RedisStream(r, name)
    try:
        ids = _publish(db, 3)
        assert relay(db, stream, DEMO_NOW) == 3
        seen: list[str] = []
        c = Consumer("rc", {"WindowClosed": lambda s, e: seen.append(e.event_id)})
        consume(db, stream, c, DEMO_NOW)
        assert seen == ids
        assert consume(db, stream, c, DEMO_NOW) == 0
    finally:
        r.delete(name)
