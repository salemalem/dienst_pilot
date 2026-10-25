"""Privacy rules, checked on every GET endpoint for every persona."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from dienstpilot.app.deps import get_engines

from .helpers import future_shift, walk

pytestmark = pytest.mark.db
PERSONAS = ["kaya", "weber", "lorenz", "brandt", "hoffmann", "vogel", "it-admin"]
FORBIDDEN_KEYS = (
    "diagnos",
    "requester_reason",
    "personal_reason",
    "leave_reason",
    "icd",
    "p_accept",  # C5's probability of accepting a cover request is never returned to anyone
    "accept_prob",
)
QUERIES = {
    "/roster": "?month=2026-11",
    "/me/roster": "?month=2026-11",
    "/planner/runs": "?month=2026-12",
    "/planner/history": "?month=2026-11",
    "/compliance/hours": "?month=2026-10",
    "/rules/search": "?q=Ruhezeit",
}


def _get_paths(client: TestClient, cascade_id: str, assignment_id: str) -> list[str]:
    """Every GET path of the OpenAPI schema, with path and required query parameters filled in."""
    paths = []
    for path, ops in client.app.openapi()["paths"].items():  # type: ignore[attr-defined]
        if "get" not in ops or path.startswith("/health"):
            continue  # health checks carry no data (and /health/ready needs Redis)
        p = path.replace("{month}", "2026-12").replace("{cascade_id}", cascade_id)
        if p in ("/me/swaps/audience", "/planner/cover-candidates"):
            p += f"?assignment_id={assignment_id}"
        paths.append(p + QUERIES.get(path, ""))
    return paths


@pytest.fixture
def live(client: TestClient, login: Any) -> dict[str, str]:
    """A sick report with an open cover search, so absences appear everywhere."""
    weber = login("weber")
    shift = future_shift(client, weber)
    r = client.post(
        "/me/sick", json={"start_date": shift["date"], "end_date": shift["date"]}, headers=weber
    )
    assert r.status_code == 201, r.text
    cascades = client.get("/planner/cascades", headers=login("brandt")).json()
    open_ones = [c for c in cascades if c["status"] in ("open", "pending_approval")]
    assert open_ones
    kaya_shift = future_shift(client, login("kaya"))
    return {"cascade_id": open_ones[0]["id"], "assignment_id": kaya_shift["assignment_id"]}


def test_every_get_endpoint_respects_the_privacy_rules(
    client: TestClient, login: Any, live: dict[str, str]
) -> None:
    paths = _get_paths(client, live["cascade_id"], live["assignment_id"])
    assert len(paths) >= 30
    planner_saw_category = False
    for persona in PERSONAS:
        h = login(persona)
        for path in paths:
            r = client.get(path, headers=h)
            assert r.status_code in (200, 403, 404), (persona, path, r.status_code, r.text[:200])
            if r.status_code != 200:
                continue
            pairs = walk(r.json())
            for key, _value in pairs:
                assert not (key and any(f in key.lower() for f in FORBIDDEN_KEYS)), (
                    persona,
                    path,
                    key,
                )
            if persona in ("brandt", "hoffmann"):
                planner_saw_category |= any(k == "category" and v == "sick" for k, v in pairs)
                continue
            assert not any(k == "category" for k, _ in pairs), (persona, path)
            assert not any(v == "sick" for _, v in pairs), (persona, path)
    assert planner_saw_category, (
        "the Planner should see absence categories (otherwise the test proves nothing)"
    )


def test_audit_trail_hides_absence_categories_from_oversight(
    client: TestClient, login: Any, live: dict[str, str]
) -> None:
    oversight = client.get("/audit/events?action=absence.&limit=50", headers=login("vogel")).json()
    planner = client.get("/audit/events?action=absence.&limit=50", headers=login("brandt")).json()
    assert oversight["total"] > 0 and oversight["total"] == planner["total"]
    assert all("category" not in e["payload"] for e in oversight["events"])
    assert all(e["payload"].get("category") == "sick" for e in planner["events"])


def test_staff_see_only_their_own_hours_and_anonymous_fairness(
    client: TestClient, login: Any
) -> None:
    kaya = login("kaya")
    assert client.get("/fairness", headers=kaya).status_code == 403
    assert client.get("/compliance/hours?month=2026-10", headers=kaya).status_code == 403
    mine = client.get("/me/fairness", headers=kaya).json()
    assert not any(k in ("staff_id", "display_name") for k, _ in walk(mine["categories"]))
    hours = client.get("/me/hours", headers=kaya).json()
    assert set(hours) >= {"contract_hours", "planned_hours", "overtime_hours"}


def test_oversight_gets_hours_per_person_but_fairness_without_names(
    client: TestClient, login: Any
) -> None:
    vogel = login("vogel")
    fair = client.get("/fairness", headers=vogel).json()
    assert fair["people"] is None and fair["distributions"]
    hours = client.get("/compliance/hours?month=2026-10", headers=vogel).json()
    assert hours["people"] and all("display_name" in p for p in hours["people"])
    assert client.get("/fairness", headers=login("brandt")).json()["people"]


def test_colleagues_on_shift_show_no_absence_reason(
    client: TestClient, login: Any, live: dict[str, str]
) -> None:
    grid = client.get("/roster?month=2026-11", headers=login("lorenz")).json()
    absences = [c["absence"] for row in grid["rows"] for c in row["cells"].values() if c["absence"]]
    assert absences and all(a == {"status": "absent"} for a in absences)


INFERRED_KEYS = ("suggestions", "suggestions_engine", "department_rate", "probability")


def test_inferred_preferences_appear_only_on_the_persons_own_wishes_endpoint(
    client: TestClient, login: Any, live: dict[str, str]
) -> None:
    """C4 output is the person's own: no other endpoint carries it, for any persona."""
    paths = _get_paths(client, live["cascade_id"], live["assignment_id"])
    for persona in PERSONAS:
        h = login(persona)
        for path in paths:
            if path == "/me/wishes":
                continue
            r = client.get(path, headers=h)
            if r.status_code != 200:
                continue
            keys = {k for k, _ in walk(r.json()) if k}
            assert not keys & set(INFERRED_KEYS), (persona, path, keys & set(INFERRED_KEYS))


def test_oversight_and_admin_cannot_ask_for_suggestions_and_planner_views_carry_none(
    client: TestClient, login: Any
) -> None:
    for persona in ("vogel", "it-admin"):
        assert client.get("/me/wishes", headers=login(persona)).status_code == 403
    # the planner sees the wishes people confirmed, never what the model infers about anybody
    for path in ("/planner/runs?month=2026-12", "/roster?month=2026-11"):
        body = client.get(path, headers=login("brandt")).json()
        assert not {k for k, _ in walk(body) if k} & set(INFERRED_KEYS), path


def test_with_suggestions_switched_off_nothing_is_inferred(client: TestClient, login: Any) -> None:
    """M12 off: the learner is never called, so nothing is computed (and nothing is stored)."""
    from dienstpilot.engines.registry import default_engines

    calls: list[int] = []
    engines = default_engines()
    real = engines.preferences.suggest

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    engines.preferences.suggest = counting  # type: ignore[method-assign]
    client.app.dependency_overrides[get_engines] = lambda: engines  # type: ignore[attr-defined]
    kaya = login("kaya")
    assert (
        client.put("/me/settings", json={"preference_suggestions": False}, headers=kaya).status_code
        == 200
    )
    audit_before = client.get("/audit/events?limit=1", headers=login("vogel")).json()["total"]
    body = client.get("/me/wishes", headers=kaya).json()
    assert body["suggestions"] == [] and calls == []
    assert (
        client.get("/audit/events?limit=1", headers=login("vogel")).json()["total"] == audit_before
    )
    client.put("/me/settings", json={"preference_suggestions": True}, headers=kaya)
    client.get("/me/wishes", headers=kaya)
    assert calls == [1]  # on again: computed once, on request
