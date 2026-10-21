from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db

GET_RULES = [
    # (path, personas allowed)
    ("/me/today", {"kaya", "lorenz", "brandt"}),
    ("/me/hours", {"kaya", "lorenz", "brandt"}),
    ("/roster?month=2026-11", {"lorenz", "brandt"}),
    ("/planner/overview", {"brandt"}),
    ("/planner/requests", {"brandt"}),
    ("/planner/cascades", {"brandt"}),
    ("/fairness", {"brandt", "vogel"}),
    ("/compliance/hours?month=2026-10", {"brandt", "vogel"}),
    ("/oversight/summary", {"brandt", "vogel"}),
    ("/audit/events", {"brandt", "vogel"}),
    ("/master-data", {"brandt", "it-admin"}),
    ("/transparency/components", {"kaya", "lorenz", "brandt", "vogel", "it-admin"}),
]
PERSONAS = ["kaya", "lorenz", "brandt", "vogel", "it-admin"]


@pytest.mark.parametrize(("path", "allowed"), GET_RULES)
def test_read_access_by_role(client: TestClient, login: Any, path: str, allowed: set[str]) -> None:
    for persona in PERSONAS:
        code = client.get(path, headers=login(persona)).status_code
        assert (code == 200) == (persona in allowed), (persona, path, code)
        assert code in (200, 403), (persona, path, code)


WRITES = [
    ("put", "/me/settings", {"theme": "dark"}),
    ("post", "/me/sick", {}),
    ("post", "/me/leave", {"start_date": "2027-03-01", "end_date": "2027-03-05"}),
    ("post", "/copilot/proposals", {"title": "x", "body": "y"}),
    ("post", "/planner/windows/2026-12/reminders", None),
    (
        "post",
        "/admin/rule-sets",
        {
            "version": "2027-1",
            "effective_from": "2027-01-01",
            "rules": {},
            "change_note_de": "x",
            "change_note_en": "x",
        },
    ),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
def test_oversight_is_read_only(
    client: TestClient, login: Any, method: str, path: str, body: Any
) -> None:
    r = getattr(client, method)(path, json=body, headers=login("vogel"))
    assert r.status_code == 403, r.text


def test_only_the_planner_decides_and_only_the_admin_changes_rules(
    client: TestClient, login: Any
) -> None:
    body = {"approve": True}
    for persona in ("kaya", "lorenz", "vogel", "it-admin"):
        assert (
            client.post(
                "/planner/leave/00000000-0000-0000-0000-000000000000/decision",
                json=body,
                headers=login(persona),
            ).status_code
            == 403
        )
    rule = {
        "version": "2027-1",
        "effective_from": "2027-01-01",
        "rules": {},
        "change_note_de": "x",
        "change_note_en": "x",
    }
    assert client.post("/admin/rule-sets", json=rule, headers=login("brandt")).status_code == 403


def test_admin_has_no_daily_operation(client: TestClient, login: Any) -> None:
    h = login("it-admin")
    assert client.get("/me/today", headers=h).status_code == 403
    assert client.get("/planner/overview", headers=h).status_code == 403
