"""CORS exists only in DEMO_MODE and only for the configured dev origins (ADR-011)."""

from fastapi.testclient import TestClient

from dienstpilot.main import create_app
from dienstpilot.shared.settings import Settings

PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type",
}


def _client(demo_mode: bool) -> TestClient:
    return TestClient(create_app(Settings(demo_mode=demo_mode)))


def test_a_dev_origin_may_call_the_api_in_demo_mode() -> None:
    r = _client(True).options(
        "/auth/demo-login", headers={"Origin": "http://localhost:8081", **PREFLIGHT}
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8081"
    assert "access-control-allow-credentials" not in r.headers
    simple = _client(True).get("/health", headers={"Origin": "http://localhost:8083"})
    assert simple.headers["access-control-allow-origin"] == "http://localhost:8083"


def test_another_origin_is_refused_in_demo_mode() -> None:
    r = _client(True).options(
        "/auth/demo-login", headers={"Origin": "https://evil.example", **PREFLIGHT}
    )
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_without_demo_mode_the_api_sends_no_cors_headers() -> None:
    r = _client(False).get("/health", headers={"Origin": "http://localhost:8081"})
    assert "access-control-allow-origin" not in r.headers
    pre = _client(False).options(
        "/auth/demo-login", headers={"Origin": "http://localhost:8081", **PREFLIGHT}
    )
    assert "access-control-allow-origin" not in pre.headers
