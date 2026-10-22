"""Upgrading a pre-Phase-9 database: seeded and app-written events are chained by migration 0007."""

import json
import os
import subprocess
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from dienstpilot.audit import service

REPO = Path(__file__).resolve().parents[2]
DB = "dienstpilot_upgrade_scratch"
DEP = str(uuid.UUID(int=77))
pytestmark = pytest.mark.db


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(["alembic", *args], check=True, cwd=REPO / "backend", env=env)


@pytest.fixture
def scratch(database_url: str) -> Iterator[str]:
    """A throw-away database on the same server as the test database."""
    base = make_url(database_url)
    admin = create_engine(base.set(database=base.database), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{DB}"'))
        c.execute(text(f'CREATE DATABASE "{DB}"'))
    url = base.set(database=DB).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)'))
        admin.dispose()


def _insert(url: str, rows: list[dict[str, object]]) -> None:
    eng = create_engine(url)
    with eng.begin() as c:
        for r in rows:
            c.execute(
                text(
                    "INSERT INTO audit.event (id, occurred_at, department_id, actor_user_id,"
                    " actor_label, action, subject_type, subject_id, staff_id, payload)"
                    " VALUES (:id, :at, :dep, NULL, :actor, :action, 'x', :sid, NULL,"
                    " CAST(:payload AS jsonb))"
                ),
                r,
            )
    eng.dispose()


def _old_history() -> list[dict[str, object]]:
    t0 = datetime(2026, 1, 1, 8, tzinfo=UTC)
    seeded = [  # deterministic ids, as the seed loader wrote them
        {
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"dienstpilot/audit/s{i}"),
            "at": t0 + timedelta(hours=i // 3),
            "dep": DEP,
            "actor": "Import",
            "action": "roster.published",
            "sid": None,
            "payload": json.dumps({"roster_month": "2026-01-01", "n": i}),
        }
        for i in range(12)
    ]
    app = [  # random ids, several at the same demo instant, with non-ASCII text
        {
            "id": uuid.uuid4(),
            "at": datetime(2026, 10, 20, 6, 0, tzinfo=UTC),
            "dep": DEP,
            "actor": "Dr. Jörg Müller",
            "action": "policy.changed",
            "sid": str(uuid.uuid4()),
            "payload": json.dumps({"auto_approve_swaps": bool(i % 2), "ratio": 1.5}),
        }
        for i in range(5)
    ]
    return seeded + app


def test_upgrade_chains_seeded_and_app_written_events(scratch: str) -> None:
    _alembic(scratch, "upgrade", "0006")
    history = _old_history()
    _insert(scratch, history)
    _alembic(scratch, "upgrade", "head")
    eng = create_engine(scratch)
    with Session(eng) as s:
        res = service.verify_chain(s, DEP)
        assert res.ok and res.rows == len(history) and res.head_seq == len(history)
        # New events written by the application after the upgrade extend the same chain.
        service.record(
            s,
            occurred_at=datetime(2026, 10, 21, tzinfo=UTC),
            department_id=DEP,
            actor_user_id=None,
            actor_label="After",
            action="test.after",
            subject_type="t",
        )
        s.commit()
        again = service.verify_chain(s, DEP)
        assert again.ok and again.rows == len(history) + 1
        # The required columns are required now.
        with pytest.raises(Exception, match=r"null value|not-null"):
            s.execute(text("UPDATE audit.event SET hash = NULL WHERE seq = 1"))
        s.rollback()
        # Tampering with the upgraded history is detected.
        s.execute(text("UPDATE audit.event SET actor_label = 'Someone' WHERE seq = 4"))
        s.commit()
        bad = service.verify_chain(s, DEP)
        assert not bad.ok and bad.first_bad_seq == 4
    eng.dispose()


def test_upgrade_is_deterministic_and_reversible(scratch: str) -> None:
    _alembic(scratch, "upgrade", "0006")
    _insert(scratch, _old_history())
    _alembic(scratch, "upgrade", "head")
    eng = create_engine(scratch)
    with eng.connect() as c:
        first = c.execute(text("SELECT hash FROM audit.event ORDER BY seq")).scalars().all()
    eng.dispose()
    _alembic(scratch, "downgrade", "0006")
    _alembic(scratch, "upgrade", "head")
    eng = create_engine(scratch)
    with eng.connect() as c:
        second = c.execute(text("SELECT hash FROM audit.event ORDER BY seq")).scalars().all()
    eng.dispose()
    assert first == second and len(first) == len(_old_history())
