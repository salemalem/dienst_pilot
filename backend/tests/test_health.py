import pytest
from fastapi.testclient import TestClient

from dienstpilot import health
from dienstpilot.health import CheckStatus
from dienstpilot.main import app
from dienstpilot.shared.settings import Settings

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _fake_checks(
    monkeypatch: pytest.MonkeyPatch, pg: CheckStatus, vec: CheckStatus, rd: CheckStatus
) -> None:
    async def fake_pg(_: Settings) -> tuple[CheckStatus, CheckStatus]:
        return pg, vec

    async def fake_redis(_: Settings) -> CheckStatus:
        return rd

    monkeypatch.setattr(health, "check_postgres", fake_pg)
    monkeypatch.setattr(health, "check_redis", fake_redis)


def test_ready_when_all_services_up(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_checks(monkeypatch, "ok", "ok", "ok")
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": "ok", "pgvector": "ok", "redis": "ok"}


@pytest.mark.parametrize(
    ("pg", "vec", "rd"),
    [("fail", "fail", "ok"), ("ok", "fail", "ok"), ("ok", "ok", "fail")],
)
def test_not_ready_when_a_check_fails(
    monkeypatch: pytest.MonkeyPatch, pg: CheckStatus, vec: CheckStatus, rd: CheckStatus
) -> None:
    _fake_checks(monkeypatch, pg, vec, rd)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "fail"


def test_unreachable_services_report_fail() -> None:
    import asyncio

    settings = Settings(
        database_url="postgresql+psycopg://x:x@127.0.0.1:1/x", redis_url="redis://127.0.0.1:1/0"
    )
    assert asyncio.run(health.check_postgres(settings)) == ("fail", "fail")
    assert asyncio.run(health.check_redis(settings)) == "fail"
