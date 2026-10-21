"""The three situations of PROCESS §4 and the other writes, end to end through the API."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dienstpilot.shared.settings import DEMO_NOW

from .helpers import future_shift

pytestmark = pytest.mark.db


def _actions(client: TestClient, login: Any, prefix: str) -> list[str]:
    page = client.get(
        f"/audit/events?action={prefix}&since=2026-10-20T00:00:00%2B02:00&limit=100",
        headers=login("brandt"),
    ).json()
    return [e["action"] for e in page["events"]]


def _report_sick(client: TestClient, login: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    weber = login("weber")
    shift = future_shift(client, weber)
    r = client.post(
        "/me/sick", json={"start_date": shift["date"], "end_date": shift["date"]}, headers=weber
    )
    assert r.status_code == 201 and r.json()["cover_searches_started"] >= 1
    assert "category" not in r.json() and r.json()["status"] == "absent"
    cascade = next(
        c
        for c in client.get("/planner/cascades", headers=login("brandt")).json()
        if c["date"] == shift["date"] and c["shift_type"] == shift["shift_type"]
    )
    return shift, cascade


def _staff_ids(client: TestClient, login: Any, month: str) -> dict[str, str]:
    rows = client.get(f"/roster?month={month}", headers=login("brandt")).json()["rows"]
    return {r["display_name"]: r["staff_id"] for r in rows}


def test_situation_c_cover_accepted_then_confirmed(
    client: TestClient, login: Any, as_staff: Any, clock: Any
) -> None:
    shift, cascade = _report_sick(client, login)
    assert cascade["timeline"][0]["response"] == "pending"
    # The first colleague does not answer within 15 minutes: the cascade moves on.
    clock.value = DEMO_NOW + timedelta(minutes=16)
    detail = client.get(f"/planner/cascades/{cascade['id']}", headers=login("brandt")).json()
    steps = detail["cascade"]["timeline"]
    assert steps[0]["response"] == "no_response"
    if detail["cascade"]["status"] != "open":
        pytest.skip("only one candidate passed the basic filter")
    asked = steps[-1]
    assert asked["response"] == "pending" and asked["rank"] == 2
    h = as_staff(_staff_ids(client, login, shift["date"][:7])[asked["staff_name"]])
    offer = next(
        o
        for o in client.get("/me/cover-requests", headers=h).json()
        if o["shift"]["date"] == shift["date"]
    )
    assert offer["check"] == "unchecked" and 0 < offer["seconds_left"] <= 15 * 60
    assert offer["hours"]["planned_hours_after"] > offer["hours"]["planned_hours_before"]
    resp = client.post(
        f"/me/cover-requests/{offer['offer_id']}", json={"accept": True}, headers=h
    ).json()
    assert resp == {"status": "pending_approval", "escalation_reason": "validator_unavailable"}
    inbox = client.get("/planner/requests", headers=login("brandt")).json()
    assert any(c["id"] == cascade["id"] for c in inbox["cascades"])
    closed = client.post(
        f"/planner/cascades/{cascade['id']}/decision",
        json={"option": "confirm_cover"},
        headers=login("brandt"),
    ).json()
    assert (
        closed["status"] == "closed"
        and closed["outcome"] == "covered"
        and closed["covered_by"] == asked["staff_name"]
    )
    actions = _actions(client, login, "")
    assert {"absence.reported", "cover.search_started", "cover.accepted", "cover.decided"} <= set(
        actions
    )


def test_situation_c_exhausted_list_escalates_with_ranked_options(
    client: TestClient, login: Any, clock: Any
) -> None:
    _, cascade = _report_sick(client, login)
    clock.value = DEMO_NOW + timedelta(hours=12)  # nobody answers: every request times out
    detail = client.get(f"/planner/cascades/{cascade['id']}", headers=login("brandt")).json()
    assert detail["cascade"]["status"] == "pending_approval"
    assert detail["cascade"]["escalation_reason"] == "list_exhausted"
    kinds = [o["kind"] for o in detail["options"]]
    assert kinds[-2:] == ["locum", "unfilled"]
    closed = client.post(
        f"/planner/cascades/{cascade['id']}/decision",
        json={"option": "locum"},
        headers=login("brandt"),
    ).json()
    assert closed["outcome"] == "locum"


def test_situation_b_swap_waits_for_the_planner(client: TestClient, login: Any) -> None:
    mehta = login("mehta")
    shift = future_shift(client, mehta)
    audience = client.get(
        f"/me/swaps/audience?assignment_id={shift['assignment_id']}", headers=mehta
    ).json()
    assert audience["check"] == "unchecked" and audience["eligible_colleagues"] >= 0
    offered = client.post(
        "/me/swaps", json={"assignment_id": shift["assignment_id"]}, headers=mehta
    )
    assert offered.status_code == 201 and offered.json()["status"] == "open"
    taker = None
    for persona in ("lorenz", "alvarez", "kaya", "nowak", "weber", "schulz"):
        offers = client.get("/me/swap-offers", headers=login(persona)).json()
        match = next((o for o in offers if o["swap_id"] == offered.json()["id"]), None)
        if match:
            taker = persona
            break
    if taker is None:
        pytest.skip("no demo persona is eligible for this shift")
    taken = client.post(f"/me/swap-offers/{offered.json()['id']}/take", headers=login(taker)).json()
    assert (
        taken["status"] == "pending_approval"
        and taken["escalation_reason"] == "validator_unavailable"
    )
    d = client.post(
        f"/planner/swaps/{offered.json()['id']}/decision",
        json={"approve": True},
        headers=login("brandt"),
    )
    assert d.json()["status"] == "approved"
    roster = client.get(f"/me/roster?month={shift['date'][:7]}", headers=login(taker)).json()
    assert any(
        s["assignment_id"] == shift["assignment_id"] and s["changed"]
        for day in roster["days"]
        for s in day["shifts"]
    )


def test_situation_a_leave_without_trade_and_planner_decline(
    client: TestClient, login: Any
) -> None:
    kaya = login("kaya")
    check = client.post(
        "/me/leave/check", json={"start_date": "2027-07-14", "end_date": "2027-07-27"}, headers=kaya
    ).json()
    assert check["engine"]["implementation"] == "stand-in" and check["trade_off"] is None
    with_trade = client.post(
        "/me/leave",
        json={"start_date": "2027-07-14", "end_date": "2027-07-27", "with_trade": True},
        headers=kaya,
    )
    assert with_trade.status_code == 501 and with_trade.json()["detail"]["component"] == "C1"
    created = client.post(
        "/me/leave", json={"start_date": "2027-07-14", "end_date": "2027-07-27"}, headers=kaya
    )
    assert created.status_code == 201 and created.json()["status"] == "pending"
    leave_id = created.json()["id"]
    inbox = client.get("/planner/requests", headers=login("brandt")).json()
    assert any(
        r["id"] == leave_id and r["impact"]["engine"]["component"] == "C6" for r in inbox["leave"]
    )
    no_reason = client.post(
        f"/planner/leave/{leave_id}/decision", json={"approve": False}, headers=login("brandt")
    )
    assert no_reason.status_code == 422
    reason = "Zu viele Urlaube im Juli; bitte eine Woche später."
    ok = client.post(
        f"/planner/leave/{leave_id}/decision",
        json={"approve": False, "reason": reason},
        headers=login("brandt"),
    )
    assert ok.json()["status"] == "declined"
    mine = next(r for r in client.get("/me/leave", headers=kaya).json() if r["id"] == leave_id)
    assert mine["decision_reason"] == reason
    note = client.get("/me/notifications", headers=kaya).json()
    assert any(n["kind"] == "leave_declined" for n in note)


def test_wishes_limit_important_and_count_as_answered(client: TestClient, login: Any) -> None:
    kaya = login("kaya")
    too_many = [
        {"date": f"2026-12-0{i}", "kind": "wish_work", "important": True} for i in range(1, 4)
    ]
    assert client.put("/me/wishes", json=too_many, headers=kaya).status_code == 422
    wrong_month = [{"date": "2027-01-05", "kind": "unavailable"}]
    assert client.put("/me/wishes", json=wrong_month, headers=kaya).status_code == 422
    ok = [
        {"date": "2026-12-14", "kind": "unavailable"},
        {"date": "2026-12-05", "kind": "wish_work", "shift_type": "nacht", "important": True},
    ]
    saved = client.put("/me/wishes", json=ok, headers=kaya).json()
    assert saved["answered_at"] is not None and len(saved["entries"]) == 2
    window = client.get("/planner/windows/2026-12", headers=login("brandt")).json()
    assert window["responded"] == 22
    parsed = client.post(
        "/me/wishes/parse",
        json={"text": "Lieber Nächte als Wochenenden, am 14.12. kann ich nicht"},
        headers=kaya,
    ).json()
    assert parsed["prefer_shifts"] == ["nacht"] and parsed["avoid_weekends"] is True
    assert parsed["unavailable"] == ["2026-12-14"] and parsed["engine"]["component"] == "C7"


def test_c1_and_c2_answer_501(client: TestClient, login: Any) -> None:
    h = login("brandt")
    for method, path, body, component in [
        ("post", "/planner/runs", {"roster_month": "2026-12"}, "C1"),
        ("post", "/planner/validate", {"roster_month": "2026-11"}, "C2"),
        ("patch", "/planner/roster/assignments", {"assignment_id": "x", "reason": "y"}, "C2"),
        ("post", "/planner/variants/x/publish", None, "C2"),
    ]:
        r = getattr(client, method)(path, json=body, headers=h)
        assert r.status_code == 501, (path, r.text)
        assert (
            r.json()["detail"]["component"] == component
            and r.json()["detail"]["planned_phase"] == 7
        )


def test_copilot_answers_with_rule_citation_and_creates_only_proposals(
    client: TestClient, login: Any
) -> None:
    h = login("brandt")
    a = client.post(
        "/copilot/ask",
        json={"question": "Warum hat Dr. Weber im Dezember zwei Wochenenden?"},
        headers=h,
    ).json()
    assert a["understood"] and a["citations"] and a["engine"]["implementation"] == "stand-in"
    assert "2026-1" in a["citations"][0]
    p = client.post(
        "/copilot/proposals",
        json={
            "title": "Reserve 27.10.",
            "body": "Reserve im Frühdienst",
            "roster_month": "2026-10",
        },
        headers=h,
    )
    assert p.status_code == 201
    assert any(
        x["id"] == p.json()["id"]
        for x in client.get("/planner/requests", headers=h).json()["proposals"]
    )
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    assert not any("copilot" in path and ("publish" in path or "approve" in path) for path in paths)


def test_transparency_lists_eight_components_none_can_change_the_roster(
    client: TestClient, login: Any
) -> None:
    comps = client.get("/transparency/components", headers=login("kaya")).json()
    assert [c["component"] for c in comps] == [f"C{i}" for i in range(1, 9)]
    assert {c["component"] for c in comps if c["implementation"] == "not_implemented"} == {
        "C1",
        "C2",
    }
    assert {c["component"] for c in comps if c["implementation"] == "stand-in"} == {
        f"C{i}" for i in range(3, 9)
    }
    assert not any(c["can_change_roster"] for c in comps)


def test_admin_adds_a_future_rule_version(client: TestClient, login: Any) -> None:
    h = login("it-admin")
    current = client.get("/master-data", headers=h).json()["rule_sets"][-1]["rules"]
    body = {
        "version": "2027-1",
        "effective_from": "2027-01-01",
        "rules": {**current, "max_on_call_per_month": 5},
        "change_note_de": "Bis zu fünf Bereitschaftsdienste.",
        "change_note_en": "Up to five on-call duties.",
    }
    assert client.post("/admin/rule-sets", json=body, headers=h).status_code == 201
    assert client.post("/admin/rule-sets", json=body, headers=h).status_code == 409
    past = {**body, "version": "2026-2", "effective_from": "2026-01-01"}
    assert client.post("/admin/rule-sets", json=past, headers=h).status_code == 422
    assert "rule_set.added" in _actions(client, login, "rule_set.")


def test_settings_round_trip(client: TestClient, login: Any) -> None:
    h = login("kaya")
    s = client.put("/me/settings", json={"language": "en", "theme": "dark"}, headers=h).json()
    assert s["language"] == "en" and s["theme"] == "dark"
    assert client.get("/me/settings", headers=h).json()["theme"] == "dark"
