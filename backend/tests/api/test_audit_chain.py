"""The hash-chained audit trail: chaining, verification, tampering, determinism (ADR-016)."""

import importlib.util
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from dienstpilot.audit import chain, service
from dienstpilot.audit.seed import chain_events
from dienstpilot.shared.settings import DEMO_NOW

pytestmark = pytest.mark.db
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def db(app_factory: Any) -> Any:
    with Session(bind=app_factory.conn, join_transaction_mode="create_savepoint") as s:
        yield s


@pytest.fixture
def dep(db: Session) -> str:
    return str(db.execute(text("SELECT id FROM organization.department")).scalar_one())


def _append(db: Session, dep: str | None, n: int = 1) -> None:
    for i in range(n):
        service.record(
            db,
            occurred_at=DEMO_NOW + timedelta(minutes=i),
            department_id=dep,
            actor_user_id=None,
            actor_label="Test",
            action="test.event",
            subject_type="test",
            payload={"i": i, "text": "Größe ä"},
        )


def test_seeded_history_is_one_verified_chain(db: Session, dep: str) -> None:
    res = service.verify_chain(db, dep)
    assert res.ok and res.rows > 1000 and res.head_seq == res.rows
    st = service.chain_status(db, dep, DEMO_NOW)
    assert st.state == "verified" and st.trigger == "seed"


def test_new_events_extend_the_chain_and_are_checked_cheaply(db: Session, dep: str) -> None:
    before = service.verify_chain(db, dep)
    _append(db, dep, 3)
    st = service.chain_status(db, dep, DEMO_NOW)
    assert st.state == "verified" and st.newer_events == 3
    after = service.verify_chain(db, dep)
    assert after.ok and after.rows == before.rows + 3


def test_events_without_a_department_form_the_system_chain(db: Session, dep: str) -> None:
    _append(db, None, 2)
    res = service.verify_chain(db, chain.SYSTEM_CHAIN)
    assert res.ok and res.rows == 2
    assert service.verify_chain(db, dep).ok


def _tamper(db: Session, sql: str, **params: Any) -> None:
    db.execute(text(sql), params)
    db.flush()


def test_changing_one_row_is_detected(db: Session, dep: str) -> None:
    seq = 1000
    _tamper(
        db,
        "UPDATE audit.event SET actor_label = 'Someone else' WHERE chain_key = :k AND seq = :s",
        k=dep,
        s=seq,
    )
    res = service.verify_chain(db, dep)
    assert not res.ok and res.first_bad_seq == seq and "content" in (res.reason or "")


def test_changing_a_payload_is_detected(db: Session, dep: str) -> None:
    _tamper(
        db,
        "UPDATE audit.event SET payload = payload || '{\"x\": 1}'::jsonb "
        "WHERE chain_key = :k AND seq = 7",
        k=dep,
    )
    assert service.verify_chain(db, dep).first_bad_seq == 7


def test_deleting_a_row_is_detected(db: Session, dep: str) -> None:
    _tamper(db, "DELETE FROM audit.event WHERE chain_key = :k AND seq = 500", k=dep)
    res = service.verify_chain(db, dep)
    assert not res.ok and res.first_bad_seq == 500 and "gap" in (res.reason or "")


def test_deleting_the_newest_rows_is_detected(db: Session, dep: str) -> None:
    _append(db, dep, 2)
    head = service.verify_chain(db, dep).head_seq
    _tamper(db, "DELETE FROM audit.event WHERE chain_key = :k AND seq = :s", k=dep, s=head)
    res = service.verify_chain(db, dep)
    assert not res.ok and res.first_bad_seq == head


def test_rewriting_a_row_and_its_hash_breaks_the_next_link(db: Session, dep: str) -> None:
    _tamper(
        db,
        "UPDATE audit.event SET actor_label = 'X', hash = repeat('a', 64) "
        "WHERE chain_key = :k AND seq = 300",
        k=dep,
    )
    res = service.verify_chain(db, dep)
    assert not res.ok and res.first_bad_seq == 300  # the row no longer matches its own hash


def test_a_failed_check_is_what_w10_shows(db: Session, dep: str) -> None:
    _tamper(db, "UPDATE audit.event SET action = 'x' WHERE chain_key = :k AND seq = 42", k=dep)
    service.run_check(db, dep, DEMO_NOW, "on_demand")
    st = service.chain_status(db, dep, DEMO_NOW)
    assert st.state == "failed" and st.first_bad_seq == 42


def test_a_check_older_than_36_hours_is_stale(db: Session, dep: str) -> None:
    st = service.chain_status(db, dep, DEMO_NOW + timedelta(hours=37))
    assert st.state == "stale"
    assert service.chain_status(db, dep, DEMO_NOW + timedelta(hours=35)).state == "verified"


def test_never_checked_is_not_verified(db: Session, dep: str) -> None:
    db.execute(text("DELETE FROM audit.chain_check"))
    assert service.chain_status(db, dep, DEMO_NOW).state == "never_checked"


def test_new_event_after_a_tampered_tail_is_not_called_verified(db: Session, dep: str) -> None:
    _append(db, dep, 2)
    head = service.verify_chain(db, dep).head_seq
    _tamper(
        db, "UPDATE audit.event SET action = 'x' WHERE chain_key = :k AND seq = :s", k=dep, s=head
    )
    st = service.chain_status(db, dep, DEMO_NOW)
    assert st.state == "failed" and st.first_bad_seq == head


# --- through the API ---------------------------------------------------------------------------


def test_w10_reports_the_real_state(client: Any, login: Any, app_factory: Any, dep: str) -> None:
    h = login("brandt")
    page = client.get("/audit/events?limit=5", headers=h).json()
    assert page["chain"]["state"] == "verified" and page["chain"]["trigger"] == "seed"
    assert [e["seq"] for e in page["events"]] == sorted(
        (e["seq"] for e in page["events"]), reverse=True
    )
    app_factory.conn.execute(
        text("UPDATE audit.event SET actor_label = 'x' WHERE chain_key = :k AND seq = 10"),
        {"k": dep},
    )
    r = client.post("/audit/verify", headers=h)
    assert (
        r.status_code == 200 and r.json()["state"] == "failed" and r.json()["first_bad_seq"] == 10
    )
    assert client.get("/audit/events", headers=h).json()["chain"]["state"] == "failed"


def test_verify_is_for_planner_and_oversight_only(client: Any, login: Any) -> None:
    assert client.post("/audit/verify", headers=login("kaya")).status_code == 403
    assert client.post("/audit/verify", headers=login("vogel")).status_code in (200, 403)


def test_system_entries_after_the_last_check_do_not_unverify_the_log(db: Session, dep: str) -> None:
    _append(db, None, 2)  # a clock change after the seed check
    st = service.chain_status(db, dep, DEMO_NOW)
    assert st.state == "verified" and st.newer_events == 2
    _tamper(db, "UPDATE audit.event SET action = 'x' WHERE chain_key = 'system' AND seq = 1")
    st = service.chain_status(db, dep, DEMO_NOW)
    assert st.state == "failed" and st.first_bad_seq == 1


# --- determinism and format --------------------------------------------------------------------


def _fake_events(n: int) -> list[dict[str, Any]]:
    dep = uuid.UUID(int=1)
    out = []
    for i in range(n):
        out.append(
            {
                "id": uuid.UUID(int=1000 + i),
                "occurred_at": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i // 3),
                "department_id": dep if i % 7 else None,
                "actor_user_id": None,
                "actor_label": "Import",
                "action": f"a.{i % 4}",
                "subject_type": "t",
                "subject_id": None,
                "staff_id": None,
                "payload": {"n": i},
            }
        )
    return out


def test_seed_chain_does_not_depend_on_input_order() -> None:
    events = _fake_events(60)
    shuffled = events[:]
    random.Random(3).shuffle(shuffled)
    a, b = chain_events(events), chain_events(shuffled)
    assert [e["hash"] for e in a] == [e["hash"] for e in b]
    assert {e["chain_key"] for e in a} == {str(uuid.UUID(int=1)), chain.SYSTEM_CHAIN}
    assert a[0]["prev_hash"] == chain.GENESIS


def test_the_frozen_migration_copy_matches_the_application_code() -> None:
    spec = importlib.util.spec_from_file_location(
        "m0007", REPO / "backend/migrations/versions/20261022_0007_audit_hash_chain.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    row = type(
        "R",
        (),
        {
            "id": uuid.UUID(int=5),
            "occurred_at": datetime(2026, 3, 4, 5, 6, 7, 891011, tzinfo=UTC),
            "department_id": uuid.UUID(int=1),
            "actor_user_id": None,
            "actor_label": "Größe ä",
            "action": "x.y",
            "subject_type": "t",
            "subject_id": uuid.UUID(int=9),
            "staff_id": None,
            "payload": {"b": [1, 2.5, "ü"], "a": None},
        },
    )
    mine = chain.canonical(
        chain="k",
        seq=3,
        event_id=row.id,
        occurred_at=row.occurred_at,
        department_id=row.department_id,
        actor_user_id=None,
        actor_label=row.actor_label,
        action=row.action,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        staff_id=None,
        payload=row.payload,
    )
    assert mod._canonical("k", 3, row) == mine


def test_every_audit_write_goes_through_the_chain() -> None:
    """No code path may construct an Event itself (a row without hashes violates NOT NULL)."""
    offenders = []
    for path in (REPO / "backend/src/dienstpilot").rglob("*.py"):
        if path.name in ("service.py", "seed.py") and path.parent.name == "audit":
            continue
        if "Event(" in path.read_text() and "audit.models" in path.read_text():
            offenders.append(str(path))
    assert not offenders
