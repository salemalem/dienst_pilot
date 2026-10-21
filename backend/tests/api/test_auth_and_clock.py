from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dienstpilot.shared.clock import RedisClock
from dienstpilot.shared.settings import DEMO_NOW, Settings

pytestmark = pytest.mark.db
SRC = Path(__file__).resolve().parents[2] / "src"


def test_personas_follow_ui_spec(client: TestClient) -> None:
    personas = {p["key"]: p["role"] for p in client.get("/auth/personas").json()}
    assert personas["kaya"] == "staff"
    assert personas["lorenz"] == "staff_plus"
    assert personas["brandt"] == "planner"
    assert personas["vogel"] == "oversight"
    assert personas["it-admin"] == "admin"
    assert len(personas) == 11


def test_login_and_me(client: TestClient, login: Any) -> None:
    me = client.get("/me", headers=login("kaya")).json()
    assert me["display_name"] == "Dr. Aylin Kaya" and me["staff_id"]


def test_unknown_persona_and_bad_tokens(client: TestClient, login: Any, clock: Any) -> None:
    assert client.post("/auth/demo-login", json={"persona": "nobody"}).status_code == 404
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer forged.token"}).status_code == 401
    h = login("kaya")
    clock.value = DEMO_NOW + timedelta(hours=13)  # tokens last 12 hours on the demo clock
    assert client.get("/me", headers=h).status_code == 401


def test_no_code_reads_the_system_clock() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in (
            "datetime.now(",
            "date.today(",
            "time.time(",
            "datetime.utcnow(",
            "datetime.today(",
        ):
            if needle in text:
                offenders.append(f"{path.relative_to(SRC)}: {needle}")
    assert offenders == []


def test_everything_uses_the_demo_clock(client: TestClient, login: Any, clock: Any) -> None:
    h = login("kaya")
    assert client.get("/clock").json()["now"].startswith("2026-10-20T06:00")
    today = client.get("/me/today", headers=h).json()
    assert today["now"].startswith("2026-10-20T06:00")
    assert today["open_window"]["days_left"] == 6
    clock.value = DEMO_NOW + timedelta(days=3)
    assert client.get("/me/today", headers=h).status_code == 401  # tokens follow the demo clock
    assert client.get("/me/today", headers=login("kaya")).json()["open_window"]["days_left"] == 3
    clock.value = DEMO_NOW + timedelta(days=7)  # after the window closed (26.10. 23:59)
    assert client.get("/me/today", headers=login("kaya")).json()["open_window"] is None


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value.encode()

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def test_demo_clock_endpoint_only_in_demo_mode_and_only_for_admins(
    app_factory: Any, seeded: str
) -> None:
    off: TestClient = app_factory(Settings(database_url=seeded, demo_mode=False))
    token = off.post("/auth/demo-login", json={"persona": "it-admin"}).json()["access_token"]
    assert off.put(
        "/demo/clock", json={"reset": True}, headers={"Authorization": f"Bearer {token}"}
    ).status_code in (404, 405)

    on: TestClient = app_factory(Settings(database_url=seeded, demo_mode=True))
    from dienstpilot.app.deps import get_clock

    redis_clock = RedisClock(FakeRedis(), DEMO_NOW)  # type: ignore[arg-type]
    on.app.dependency_overrides[get_clock] = lambda: redis_clock  # type: ignore[attr-defined]

    def h(persona: str) -> dict[str, str]:
        return {
            "Authorization": "Bearer "
            + on.post("/auth/demo-login", json={"persona": persona}).json()["access_token"]
        }

    later = "2026-10-20T06:40:00+02:00"
    assert on.put("/demo/clock", json={"now": later}, headers=h("brandt")).status_code == 403
    r = on.put("/demo/clock", json={"now": later}, headers=h("it-admin"))
    assert r.status_code == 200 and r.json()["now"].startswith("2026-10-20T06:40")
    assert on.get("/clock").json()["now"].startswith("2026-10-20T06:40")
    assert (
        on.put("/demo/clock", json={"reset": True}, headers=h("it-admin"))
        .json()["now"]
        .startswith("2026-10-20T06:00")
    )
