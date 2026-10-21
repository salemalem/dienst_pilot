from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dienstpilot.app import jobs
from dienstpilot.app.deps import get_clock, get_engines
from dienstpilot.app.queue import get_queue
from dienstpilot.main import create_app
from dienstpilot.seeding import load
from dienstpilot.shared.database import get_session
from dienstpilot.shared.ports import Clock
from dienstpilot.shared.settings import DEMO_NOW, TZ, Settings


class MovableClock(Clock):
    """A test clock the test can move."""

    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value.astimezone(TZ)


@pytest.fixture(scope="session")
def seeded(database_url: str, seed_dir: Path) -> str:
    load(seed_dir, database_url)
    return database_url


@pytest.fixture
def clock() -> MovableClock:
    return MovableClock(DEMO_NOW)


class InlineQueue:
    """Runs a job right away inside the test transaction (the arq path has its own test)."""

    def __init__(self, conn: Any, clock: Clock) -> None:
        self.conn, self.clock, self.jobs = conn, clock, []
        self.engines: Any = None  # a test may swap in other engines for the jobs

    def enqueue(self, job: str, **kwargs: str) -> None:
        self.jobs.append((job, kwargs))
        with Session(
            bind=self.conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as s:
            jobs.JOBS[job](s, self.engines or get_engines(), self.clock, **kwargs)
            s.commit()


@pytest.fixture(autouse=True)
def fast_solver(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorter solver runs in tests, except those marked ``production_solver``."""
    from dataclasses import replace

    if request.node.get_closest_marker("production_solver"):
        return
    monkeypatch.setattr(jobs, "RUN_CONFIG", replace(jobs.RUN_CONFIG, deterministic_time=4.0))
    monkeypatch.setattr(jobs, "CHECK_CONFIG", replace(jobs.CHECK_CONFIG, deterministic_time=3.0))


@pytest.fixture
def app_factory(seeded: str, clock: MovableClock) -> Iterator[Any]:
    """Build apps whose requests share one connection; everything rolls back after the test."""
    engine = create_engine(seeded)
    conn = engine.connect()
    outer = conn.begin()

    def session_override() -> Iterator[Session]:
        with Session(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as s:
            yield s
            s.commit()

    def make(settings: Settings | None = None) -> TestClient:
        app = create_app(settings or Settings(database_url=seeded))
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_clock] = lambda: clock
        app.dependency_overrides[get_queue] = lambda: queue
        return TestClient(app)

    queue = InlineQueue(conn, clock)
    make.conn = conn  # type: ignore[attr-defined]
    make.queue = queue  # type: ignore[attr-defined]
    yield make
    outer.rollback()
    conn.close()
    engine.dispose()


@pytest.fixture
def client(app_factory: Any) -> TestClient:
    c: TestClient = app_factory()
    return c


@pytest.fixture
def login(client: TestClient) -> Any:
    def headers(persona: str) -> dict[str, str]:
        r = client.post("/auth/demo-login", json={"persona": persona})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return headers


@pytest.fixture
def as_staff(app_factory: Any, client: TestClient) -> Any:
    """Sign in as any physician (tests only): adds a temporary user inside the test transaction."""
    from sqlalchemy import text

    def headers(staff_id: str) -> dict[str, str]:
        conn = app_factory.conn
        key = f"test-{staff_id[:8]}"
        conn.execute(
            text(
                "INSERT INTO identity.user"
                " (id, persona_key, display_name, role, department_id, staff_id) "
                "SELECT gen_random_uuid(), :key, s.display_name, 'staff', s.department_id, s.id "
                "FROM organization.staff s WHERE s.id = :sid "
                "AND NOT EXISTS (SELECT 1 FROM identity.user u WHERE u.staff_id = s.id)"
            ),
            {"key": key, "sid": staff_id},
        )
        persona = conn.execute(
            text("SELECT persona_key FROM identity.user WHERE staff_id = :sid"), {"sid": staff_id}
        ).scalar_one()
        r = client.post("/auth/demo-login", json={"persona": persona})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return headers
