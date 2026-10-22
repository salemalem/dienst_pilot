"""Exactly-once and restart behaviour with real commits and several connections (ADR-017).

These tests commit to the test database (the other tests roll back), so they reload the seed
when they are done.
"""

import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dienstpilot.app import deps
from dienstpilot.app.deps import get_clock, get_engines
from dienstpilot.main import create_app
from dienstpilot.operations import service as operations
from dienstpilot.seeding import load
from dienstpilot.shared.database import get_session
from dienstpilot.shared.settings import DEMO_NOW, Settings
from dienstpilot.workflows.runtime import settle

from .conftest import MovableClock
from .test_flows import _report_sick

pytestmark = pytest.mark.db


@pytest.fixture
def live(seeded: str, seed_dir: Path) -> Iterator[tuple[Engine, MovableClock, Any]]:
    """An app on committing sessions and a movable clock; the seed is reloaded afterwards."""
    engine = create_engine(seeded, pool_size=20)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    clock = MovableClock(DEMO_NOW + timedelta(minutes=40))

    def session() -> Iterator[Session]:
        with factory() as s:
            yield s
            s.commit()

    app = create_app(Settings(database_url=seeded))
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_clock] = lambda: clock
    yield engine, clock, app
    app.dependency_overrides.clear()
    engine.dispose()
    load(seed_dir, seeded)


def _login(client: TestClient) -> Any:
    def h(persona: str) -> dict[str, str]:
        r = client.post("/auth/demo-login", json={"persona": persona})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return h


def _offers(engine: Engine, cascade_id: str) -> list[tuple[str, str]]:
    with engine.connect() as c:
        return [
            (r[0], r[1])
            for r in c.execute(
                text(
                    "SELECT staff_id::text, response FROM operations.cover_offer"
                    " WHERE cascade_id = :c ORDER BY rank"
                ),
                {"c": cascade_id},
            )
        ]


def _race(app: Any, engine: Engine, clock: MovableClock, login: Any, workers: int = 8) -> None:
    """Fire the due timers from API reads and from worker-style calls at the same moment."""
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []
    brandt = login("brandt")

    def worker(i: int) -> None:
        try:
            barrier.wait()
            if i % 2:
                with TestClient(app) as c:
                    assert c.get("/planner/cascades", headers=brandt).status_code == 200
            else:
                with Session(engine) as s:
                    settle(s, clock, get_engines())
                    s.commit()
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors


def test_two_readers_and_the_worker_never_ask_anyone_twice(live: Any) -> None:
    engine, clock, app = live
    client = TestClient(app)
    login = _login(client)
    _, cascade = _report_sick(client, login)
    cid = cascade["id"]
    before = _offers(engine, cid)
    assert [r for _, r in before] == ["pending"]
    clock.value = DEMO_NOW + timedelta(minutes=40 + 16)
    _race(app, engine, clock, login)
    after = _offers(engine, cid)
    assert after[0][1] == "no_response"
    assert len(after) <= 2 and len({s for s, _ in after}) == len(after)
    with engine.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM workflow.timer"
                " WHERE kind = 'cover.timeout' AND fired_at IS NOT NULL"
            )
        ).scalar_one()
    assert n == 1  # the first deadline fired once, whoever got there first
    # A long jump: everyone remaining is asked in order, once, from several callers at once.
    clock.value = DEMO_NOW + timedelta(hours=4)
    _race(app, engine, clock, login)
    final = _offers(engine, cid)
    assert len({s for s, _ in final}) == len(final), "nobody was asked twice"
    assert all(r == "no_response" for _, r in final)


def test_a_worker_that_dies_mid_cascade_leaves_everything_for_the_next_one(
    live: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, clock, app = live
    client = TestClient(app)
    login = _login(client)
    _, cascade = _report_sick(client, login)
    cid = cascade["id"]
    clock.value = DEMO_NOW + timedelta(minutes=40 + 16)

    class Killed(BaseException):
        """Not an Exception: the worker process is gone, nothing catches it."""

    real = operations.timeout_offer

    def die_after_writing(*a: Any, **k: Any) -> Any:
        real(*a, **k)  # the work is done in the open transaction ...
        raise Killed  # ... and the process dies before the commit

    monkeypatch.setattr(operations, "timeout_offer", die_after_writing)
    s = Session(engine)
    with pytest.raises(Killed):
        settle(s, clock, get_engines())
    s.close()  # connection drops, the transaction is rolled back
    monkeypatch.setattr(operations, "timeout_offer", real)
    assert [r for _, r in _offers(engine, cid)] == ["pending"], "nothing was half done"
    with engine.connect() as c:
        assert (
            c.execute(
                text(
                    "SELECT count(*) FROM workflow.timer WHERE kind='cover.timeout'"
                    " AND fired_at IS NULL AND cancelled_at IS NULL AND due_at <= :t"
                ),
                {"t": clock.now()},
            ).scalar_one()
            == 1
        )  # the timer is still due
    # A fresh worker starts: it resumes the cascade exactly where it was.
    with Session(engine) as fresh:
        fired = settle(fresh, clock, get_engines())
        fresh.commit()
    assert [k for k, _ in fired] == ["cover.timeout"]
    after = _offers(engine, cid)
    assert after[0][1] == "no_response" and len(after) <= 2
    with Session(engine) as again:
        assert settle(again, clock, get_engines()) == []  # and does not do it a second time
    assert deps  # keep the import used by the override above
