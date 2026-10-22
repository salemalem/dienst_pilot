"""The three situations of PROCESS §4 and the other writes, end to end through the API."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dienstpilot.shared.settings import DEMO_NOW

from .helpers import coverable_shift

pytestmark = pytest.mark.db


def _actions(client: TestClient, login: Any, prefix: str) -> list[str]:
    page = client.get(
        f"/audit/events?action={prefix}&since=2026-10-20T00:00:00%2B02:00&limit=100",
        headers=login("brandt"),
    ).json()
    return [e["action"] for e in page["events"]]


def _report_sick(client: TestClient, login: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    weber = login("weber")
    shift = coverable_shift(client, weber)
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


def test_situation_c_cover_is_policy_approved_or_escalated_with_a_reason(
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
        pytest.skip("only one colleague could take this shift under the rules")
    asked = steps[-1]
    assert asked["response"] == "pending" and asked["rank"] == 2
    h = as_staff(_staff_ids(client, login, shift["date"][:7])[asked["staff_name"]])
    offer = next(
        o
        for o in client.get("/me/cover-requests", headers=h).json()
        if o["shift"]["date"] == shift["date"]
    )
    assert offer["check"] == "validated" and 0 < offer["seconds_left"] <= 15 * 60
    resp = client.post(
        f"/me/cover-requests/{offer['offer_id']}", json={"accept": True}, headers=h
    ).json()
    if resp["status"] == "closed":
        # C2-valid, no overtime, policy on: approved by the policy, logged as such.
        assert resp["escalation_reason"] is None
        events = client.get(
            "/audit/events?action=cover.decided&since=2026-10-20T00:00:00%2B02:00",
            headers=login("brandt"),
        ).json()["events"]
        assert any(e["payload"] == {"approval": "policy"} for e in events)
    else:
        assert resp == {"status": "pending_approval", "escalation_reason": "overtime"}
        closed = client.post(
            f"/planner/cascades/{cascade['id']}/decision",
            json={"option": "confirm_cover"},
            headers=login("brandt"),
        ).json()
        assert closed["outcome"] == "covered" and closed["covered_by"] == asked["staff_name"]
    roster = client.get(f"/roster?month={shift['date'][:7]}", headers=login("brandt")).json()
    row = next(r for r in roster["rows"] if r["display_name"] == asked["staff_name"])
    assert shift["shift_type"] in row["cells"][shift["date"]]["shifts"]
    actions = _actions(client, login, "")
    assert {"absence.reported", "cover.search_started", "cover.accepted", "cover.decided"} <= set(
        actions
    )


def test_cover_waits_for_the_planner_when_the_policy_is_off(
    client: TestClient, login: Any, as_staff: Any
) -> None:
    put = client.put(
        "/planner/policy",
        json={"auto_approve_swaps": True, "auto_approve_cover": False},
        headers=login("brandt"),
    )
    assert put.status_code == 200 and put.json()["auto_approve_cover"] is False
    shift, cascade = _report_sick(client, login)
    asked = cascade["timeline"][0]
    h = as_staff(_staff_ids(client, login, shift["date"][:7])[asked["staff_name"]])
    offer = next(
        o
        for o in client.get("/me/cover-requests", headers=h).json()
        if o["shift"]["date"] == shift["date"]
    )
    resp = client.post(
        f"/me/cover-requests/{offer['offer_id']}", json={"accept": True}, headers=h
    ).json()
    assert resp["status"] == "pending_approval"
    assert resp["escalation_reason"] in ("policy_off", "overtime")
    assert "policy.changed" in _actions(client, login, "policy")


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


def _offer_and_find_taker(
    client: TestClient, login: Any, offerer: str = "nowak", needs_planner: bool = False
) -> tuple[dict[str, Any], str, str]:
    """Offer a shift whose swap does (not) break a rule for the offerer, and find a taker."""
    h = login(offerer)
    days = client.get("/me/roster?month=2026-11", headers=h).json()["days"]
    shift = None
    for d in days:
        for s in d["shifts"]:
            if s["shift_type"] == "ruf" or s["date"] <= DEMO_NOW.date().isoformat():
                continue
            a = client.get(f"/me/swaps/audience?assignment_id={s['assignment_id']}", headers=h)
            audience = a.json()
            assert audience["check"] == "validated"
            if audience["eligible_colleagues"] and audience["needs_planner"] == needs_planner:
                shift = s
                break
        if shift:
            break
    if shift is None:
        pytest.skip(f"no shift of {offerer} with needs_planner={needs_planner}")
    offered = client.post("/me/swaps", json={"assignment_id": shift["assignment_id"]}, headers=h)
    assert offered.status_code == 201 and offered.json()["status"] == "open"
    for persona in ("lorenz", "alvarez", "kaya", "mehta", "nowak", "weber", "schulz"):
        if persona == offerer:
            continue
        offers = client.get("/me/swap-offers", headers=login(persona)).json()
        if any(o["swap_id"] == offered.json()["id"] for o in offers):
            return shift, offered.json()["id"], persona
    pytest.skip("no demo persona may take this shift under the rules")


def test_the_policy_can_be_switched_several_times_at_the_same_demo_instant(
    client: TestClient, login: Any
) -> None:
    """The demo clock stands still, so each switch is its own audit event (no id collision)."""
    h = login("brandt")
    for swaps in (False, True, False, True):
        r = client.put(
            "/planner/policy",
            json={"auto_approve_swaps": swaps, "auto_approve_cover": True},
            headers=h,
        )
        assert r.status_code == 200, r.text
    assert _actions(client, login, "policy").count("policy.changed") >= 4


def test_situation_b_valid_swap_is_approved_by_the_policy(client: TestClient, login: Any) -> None:
    shift, swap_id, taker = _offer_and_find_taker(client, login)
    taken = client.post(f"/me/swap-offers/{swap_id}/take", headers=login(taker)).json()
    assert taken["status"] == "approved" and taken["escalation_reason"] is None
    events = client.get(
        "/audit/events?action=swap.approved&since=2026-10-20T00:00:00%2B02:00",
        headers=login("brandt"),
    ).json()["events"]
    assert any(e["payload"] == {"approval": "policy"} for e in events)
    roster = client.get(f"/me/roster?month={shift['date'][:7]}", headers=login(taker)).json()
    assert any(
        s["assignment_id"] == shift["assignment_id"] and s["changed"]
        for day in roster["days"]
        for s in day["shifts"]
    )


def test_situation_b_swap_waits_for_the_planner_when_the_policy_is_off(
    client: TestClient, login: Any
) -> None:
    client.put(
        "/planner/policy",
        json={"auto_approve_swaps": False, "auto_approve_cover": True},
        headers=login("brandt"),
    )
    _, swap_id, taker = _offer_and_find_taker(client, login)
    taken = client.post(f"/me/swap-offers/{swap_id}/take", headers=login(taker)).json()
    assert taken["status"] == "pending_approval" and taken["escalation_reason"] == "policy_off"
    inbox = client.get("/planner/requests", headers=login("brandt")).json()
    assert any(s["id"] == swap_id for s in inbox["swaps"])
    d = client.post(
        f"/planner/swaps/{swap_id}/decision", json={"approve": True}, headers=login("brandt")
    )
    assert d.json()["status"] == "approved"


def test_a_swap_below_the_offerers_hours_band_goes_to_the_planner(
    client: TestClient, login: Any
) -> None:
    _, swap_id, taker = _offer_and_find_taker(client, login, "mehta", needs_planner=True)
    taken = client.post(f"/me/swap-offers/{swap_id}/take", headers=login(taker)).json()
    assert taken["status"] == "pending_approval" and taken["escalation_reason"] == "hours_band"


def test_an_invalid_taker_is_refused(client: TestClient, login: Any) -> None:
    """Someone who already works that day cannot take the offer (C2: one shift per day)."""
    shift, swap_id, _ = _offer_and_find_taker(client, login)
    for persona in ("lorenz", "alvarez", "kaya", "mehta", "weber", "schulz"):
        h = login(persona)
        mine = client.get(f"/me/roster?month={shift['date'][:7]}", headers=h).json()["days"]
        busy = any(
            x["shift_type"] in ("frueh", "spaet", "nacht", "bereitschaft")
            for d in mine
            if d["date"] == shift["date"]
            for x in d["shifts"]
        )
        if busy:
            r = client.post(f"/me/swap-offers/{swap_id}/take", headers=h)
            assert r.status_code == 403
            return
    pytest.skip("no demo persona works that day")


def test_situation_a_leave_without_trade_and_planner_decline(
    client: TestClient, login: Any
) -> None:
    kaya = login("kaya")
    check = client.post(
        "/me/leave/check", json={"start_date": "2027-07-26", "end_date": "2027-08-06"}, headers=kaya
    ).json()
    assert check["engine"]["component"] == "C6" and check["trade_off_check_id"]
    # The leave spans two months: the C1 check offers no trade-off.
    result = client.get(f"/me/leave/checks/{check['trade_off_check_id']}", headers=kaya).json()
    assert result["status"] == "done" and result["engine"]["component"] == "C1"
    assert result["result"]["outcome"] == "not_applicable"
    assert result["result"]["reason"] == "spans_months"
    with_trade = client.post(
        "/me/leave",
        json={
            "start_date": "2027-07-26",
            "end_date": "2027-08-06",
            "with_trade": True,
            "check_id": check["trade_off_check_id"],
        },
        headers=kaya,
    )
    assert with_trade.status_code == 409
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


def test_w3_to_w5_run_validate_edit_and_publish(client: TestClient, login: Any) -> None:
    h = login("brandt")
    assert (
        client.post("/planner/runs", json={"roster_month": "2026-11"}, headers=h).status_code == 409
    )
    queued = client.post("/planner/runs", json={"roster_month": "2026-12"}, headers=h)
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    run = client.get(f"/planner/runs/{queued.json()['run_id']}", headers=h).json()
    assert run["status"] == "done", run
    assert run["solver_version"].startswith("c1-") and run["validator_version"].startswith("c2-")
    variants = run["variants"]
    assert [v["label"] for v in variants] == ["A", "B", "C"]
    assert sum(v["recommended"] for v in variants) == 1
    assert all(0 <= v["metrics"]["wish_rate"] <= 1 for v in variants)
    # The December request window is still open: this run is a trial and cannot be published.
    assert run["trial"] is True
    best = next(v for v in variants if v["recommended"])
    blocked = client.post(f"/planner/variants/{best['variant_id']}/publish", headers=h)
    assert blocked.status_code == 409 and "window" in blocked.json()["detail"]
    assert client.post("/planner/windows/2026-12/close", headers=h).status_code == 200
    assert client.get(f"/planner/runs/{run['run_id']}", headers=h).json()["trial"] is False
    # A second run at the same demo instant is a new run (the demo clock can stand still).
    second_run = client.post("/planner/runs", json={"roster_month": "2026-12"}, headers=h).json()
    assert second_run["run_id"] != run["run_id"]
    listed = client.get("/planner/runs?month=2026-12", headers=h).json()["runs"]
    assert {r["run_id"] for r in listed} >= {run["run_id"], second_run["run_id"]}

    grid = client.get(f"/roster?month=2026-12&variant_id={best['variant_id']}", headers=h).json()
    assert grid["status"] == "draft" and grid["rows"]
    assert (
        client.get(
            f"/roster?month=2026-12&variant_id={best['variant_id']}", headers=login("lorenz")
        ).status_code
        == 403
    )
    valid = client.post(
        "/planner/validate",
        json={"roster_month": "2026-12", "variant_id": best["variant_id"]},
        headers=h,
    ).json()
    assert valid["valid"] and valid["validator"]["component"] == "C2"

    # Remove a night from the draft: C2 reports the gap with an i18n key and a fix.
    staff_id, day, assignment_id = next(
        (row["staff_id"], day, cell["assignment_ids"][cell["shifts"].index("nacht")])
        for row in grid["rows"]
        for day, cell in row["cells"].items()
        if "nacht" in cell["shifts"]
    )
    edit = client.patch(
        "/planner/roster/assignments",
        json={"variant_id": best["variant_id"], "assignment_id": assignment_id},
        headers=h,
    ).json()
    gap = next(v for v in edit["introduced"] if v["rule"] == "coverage")
    assert gap["key"] == "violation.coverage" and gap["fix_key"] == "fix.coverage"
    assert gap["params"]["shift"] == "nacht" and gap["date"] == day
    pub = client.post(f"/planner/variants/{best['variant_id']}/publish", headers=h)
    assert pub.status_code == 422 and pub.json()["detail"]["code"] == "rule_violation"
    # Put it back: valid again, and the Planner publishes it.
    back = client.patch(
        "/planner/roster/assignments",
        json={
            "variant_id": best["variant_id"],
            "add": {"date": day, "shift_type": "nacht", "staff_id": staff_id},
        },
        headers=h,
    ).json()
    assert back["introduced"] == [] and back["violations"] == []
    pub = client.post(f"/planner/variants/{best['variant_id']}/publish", headers=h)
    assert pub.status_code == 200, pub.text
    assert pub.json()["approved_by"] == "Dr. Thomas Brandt"
    again = client.post(f"/planner/variants/{best['variant_id']}/publish", headers=h)
    assert again.status_code == 409
    statuses = {
        v["variant_id"]: v["status"]
        for v in client.get(f"/planner/runs/{run['run_id']}", headers=h).json()["variants"]
    }
    assert sorted(statuses.values()) == ["discarded", "discarded", "published"]
    second = client.get(f"/planner/runs/{second_run['run_id']}", headers=h).json()["variants"]
    assert {v["status"] for v in second} == {"discarded"}
    published = client.get("/roster?month=2026-12", headers=h).json()
    assert published["status"] == "published"
    assert "roster.published" in _actions(client, login, "roster")


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


def test_transparency_lists_eight_components_and_the_rulebook_none_can_change_the_roster(
    client: TestClient, login: Any
) -> None:
    comps = client.get("/transparency/components", headers=login("kaya")).json()
    assert [c["component"] for c in comps] == [f"C{i}" for i in range(1, 9)] + ["RAG"]
    assert {c["component"] for c in comps if c["implementation"] == "built"} == {
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "RAG",
    }
    rag = next(c for c in comps if c["component"] == "RAG")
    assert rag["eval_metric"]["served"]["method"] == "vector" and "vector" in rag["version"]
    assert {c["component"] for c in comps if c["implementation"] == "stand-in"} == {
        f"C{i}" for i in range(7, 9)
    }
    c3 = next(c for c in comps if c["component"] == "C3")
    assert c3["eval_metric"]["test_2025"][c3["eval_metric"]["champion"]["kind"]]["mae"] > 0
    c4 = next(c for c in comps if c["component"] == "C4")
    assert (
        c4["eval_metric"]["test_2025"][c4["eval_metric"]["champion"]["kind"]]["wish"]["mean_ll"] < 0
    )
    c5 = next(c for c in comps if c["component"] == "C5")
    kind = c5["eval_metric"]["champion"]["kind"]
    assert 0 < c5["eval_metric"]["test_2025"][kind]["brier"] < 1
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


def test_w1_coverage_band_comes_from_the_built_c3_forecaster(
    client: TestClient, login: Any
) -> None:
    o = client.get("/planner/overview", headers=login("brandt")).json()
    assert o["forecast_engine"]["component"] == "C3"
    assert o["forecast_engine"]["implementation"] == "built"
    assert len(o["coverage"]) == 14
    for day in o["coverage"]:
        assert 0 <= day["expected_low"] <= day["expected_absences"] <= day["expected_high"]
        assert day["expected_absences"] > 0


def test_confirming_an_avoid_chip_is_a_soft_per_shift_preference(
    client: TestClient, login: Any, app_factory: Any, clock: Any
) -> None:
    """A "rather not Spätdienst on Mondays" stays available for everything else and only moves
    the solver's soft objective: no blocked day, no change to wishes, leave or hard inputs."""
    from dataclasses import replace
    from datetime import date

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from dienstpilot.app.engine_inputs import Inputs
    from dienstpilot.app.jobs import _department
    from dienstpilot_solver.model import AvoidIn

    kaya = login("kaya")
    mondays = ["2026-12-07", "2026-12-14", "2026-12-21", "2026-12-28"]
    chip = [{"date": d, "kind": "avoid_shift", "shift_type": "spaet"} for d in mondays]
    month = date(2026, 12, 1)

    def solver_problem() -> Any:
        with Session(bind=app_factory.conn, join_transaction_mode="create_savepoint") as s:
            dept = s.execute(text("SELECT id FROM organization.department LIMIT 1")).scalar_one()
            return Inputs(s, _department(s, str(dept)), clock.now()).problem(month)

    staff_id = str(
        app_factory.conn.execute(
            text("SELECT id FROM organization.staff WHERE display_name LIKE '%Kaya'")
        ).scalar_one()
    )
    before = solver_problem()
    assert before.avoid == ()

    # A "rather not" entry names one shift and is never "important" (it is soft, not a promise).
    assert (
        client.put(
            "/me/wishes", json=[{"date": mondays[0], "kind": "avoid_shift"}], headers=kaya
        ).status_code
        == 422
    )
    assert (
        client.put("/me/wishes", json=[{**chip[0], "important": True}], headers=kaya).status_code
        == 422
    )

    saved = client.put("/me/wishes", json=chip, headers=kaya)
    assert saved.status_code == 200
    assert {(e["kind"], e["shift_type"]) for e in saved.json()["entries"]} == {
        ("avoid_shift", "spaet")
    }

    after = solver_problem()
    assert after.avoid == tuple(AvoidIn(staff_id, date.fromisoformat(d), "spaet") for d in mondays)
    blocked = after.blocked.get(staff_id, frozenset())
    assert not blocked & {date.fromisoformat(d) for d in mondays}  # never a "kann nicht"
    assert not any(w.staff_id == staff_id for w in after.wishes)  # not a "möchte arbeiten" either
    # Nothing but the soft objective changed: every hard input and every wish is identical
    # (Kaya's own answer replaced her earlier one, so compare with that answer removed).
    assert replace(after, avoid=(), wishes=(), blocked=before.blocked) == replace(
        before, wishes=(), blocked=before.blocked
    )
    assert {w for w in after.wishes if w.staff_id != staff_id} == {
        w for w in before.wishes if w.staff_id != staff_id
    }
    assert {b: v for b, v in after.blocked.items() if b != staff_id} == {
        b: v for b, v in before.blocked.items() if b != staff_id
    }
