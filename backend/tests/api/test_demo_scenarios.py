"""The three situations of PROCESS.md §4 as scripted demo scenarios (synthdata ASSUMPTIONS §19).

Only the real engines run here: C1 with its production settings, C2, and the C5 stand-in that
ranks cover. The seed carries the scenario data; these tests play the live part on the demo
clock.
"""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dienstpilot.shared.settings import DEMO_NOW

pytestmark = [pytest.mark.db, pytest.mark.production_solver]


def _shift(client: TestClient, h: dict[str, str], day: str, shift_type: str) -> dict[str, Any]:
    days = client.get(f"/me/roster?month={day[:7]}", headers=h).json()["days"]
    return next(
        s for d in days for s in d["shifts"] if s["date"] == day and s["shift_type"] == shift_type
    )


def test_a_kaya_asks_for_14_to_27_july_2027(client: TestClient, login: Any) -> None:
    """Two colleagues have already asked for overlapping days; the real M5 check runs.

    Result with the documented definition (ASSUMPTIONS §18): the leave is coverable and does
    not burden colleagues beyond the thresholds, so no trade-off is offered.
    """
    kaya = login("kaya")
    dates = {"start_date": "2027-07-14", "end_date": "2027-07-27"}
    hint = client.post("/me/leave/check", json=dates, headers=kaya).json()
    assert hint["overlapping_colleagues"] == 2
    check = client.get(f"/me/leave/checks/{hint['trade_off_check_id']}", headers=kaya).json()
    assert check["status"] == "done" and check["engine"]["component"] == "C1"
    r = check["result"]
    assert r["pending_colleague_requests_counted"] == 2
    assert r["outcome"] == "coverable" and r["trade_off"] is None, r
    assert r["impact"]["overtime_hours_delta"] <= r["thresholds"]["overtime_hours"]
    assert r["impact"]["peak_burden_delta"] <= r["thresholds"]["peak_burden"]
    # "Ohne Tausch beantragen"; the Planner sees it with the impact and approves.
    created = client.post("/me/leave", json=dates, headers=kaya)
    assert created.status_code == 201 and created.json()["trade_off"] is None
    brandt = login("brandt")
    inbox = client.get("/planner/requests", headers=brandt).json()["leave"]
    assert any(x["id"] == created.json()["id"] for x in inbox)
    ok = client.post(
        f"/planner/leave/{created.json()['id']}/decision", json={"approve": True}, headers=brandt
    )
    assert ok.json()["status"] == "approved"


def test_b_mehta_offers_saturday_21_november_and_lorenz_exchanges(
    client: TestClient, login: Any
) -> None:
    """Mehta offers his Saturday Frühdienst on 21 November 2026. Giving it away alone would put
    him below the hours band, so Lorenz takes it in exchange for her Frühdienst on Friday
    27 November; C2 finds the exchange valid for both and the policy approves it."""
    mehta, lorenz, brandt = login("mehta"), login("lorenz"), login("brandt")
    saturday = _shift(client, mehta, "2026-11-21", "frueh")
    audience = client.get(
        f"/me/swaps/audience?assignment_id={saturday['assignment_id']}", headers=mehta
    ).json()
    assert audience["needs_planner"] and audience["own_rules"] == ["contract_hours_band"]
    offered = client.post(
        "/me/swaps", json={"assignment_id": saturday["assignment_id"]}, headers=mehta
    )
    assert offered.status_code == 201
    offer = next(
        o
        for o in client.get("/me/swap-offers", headers=lorenz).json()
        if o["swap_id"] == offered.json()["id"]
    )
    friday = _shift(client, lorenz, "2026-11-27", "frueh")
    # The exchanges C2 accepts (ASSUMPTIONS §19 lists them).
    assert {(x["date"], x["shift_type"]) for x in offer["exchange_options"]} == {
        ("2026-11-27", "frueh"),
        ("2026-11-30", "spaet"),
    }
    taken = client.post(
        f"/me/swap-offers/{offered.json()['id']}/take",
        json={"give_assignment_id": friday["assignment_id"]},
        headers=lorenz,
    ).json()
    assert taken["status"] == "approved" and taken["escalation_reason"] is None
    assert taken["exchange"]["date"] == "2026-11-27"
    # Both rosters update; the Planner gets a notice (W1), not a request (W6).
    assert _shift(client, lorenz, "2026-11-21", "frueh")["changed"]
    assert _shift(client, mehta, "2026-11-27", "frueh")["changed"]
    overview = client.get("/planner/overview", headers=brandt).json()
    assert any(
        x["kind"] == "swap" and x["date"] == "2026-11-21" and x["approval"] == "policy"
        for x in overview["recent"]
    )
    assert not client.get("/planner/requests", headers=brandt).json()["swaps"]
    valid = client.post(
        "/planner/validate", json={"roster_month": "2026-11"}, headers=brandt
    ).json()
    assert valid["valid"]


def test_c_weber_reports_sick_at_0640_and_alvarez_covers(
    client: TestClient, login: Any, clock: Any
) -> None:
    """Weber's Frühdienst on Tuesday 20 October 2026 (07:30): he reports sick at 06:40, C2
    and C5 put Alvarez first, she accepts at 06:43, the policy approves, the gap is closed."""
    clock.value = DEMO_NOW + timedelta(minutes=40)
    weber, alvarez, brandt = login("weber"), login("alvarez"), login("brandt")
    early = _shift(client, weber, "2026-10-20", "frueh")
    sick = client.post(
        "/me/sick", json={"start_date": "2026-10-20", "end_date": "2026-10-20"}, headers=weber
    )
    assert sick.status_code == 201 and sick.json()["cover_searches_started"] == 1
    cascade = next(
        c
        for c in client.get("/planner/cascades", headers=brandt).json()
        if c["date"] == "2026-10-20" and c["shift_type"] == "frueh"
    )
    first = cascade["timeline"][0]
    assert first["staff_name"] == "Dr. Sofía Alvarez" and first["response"] == "pending"
    clock.value = DEMO_NOW + timedelta(minutes=43)
    request = next(
        o
        for o in client.get("/me/cover-requests", headers=alvarez).json()
        if o["shift"]["assignment_id"] == early["assignment_id"]
    )
    assert request["check"] == "validated" and request["seconds_left"] == 12 * 60
    assert request["hours"]["planned_hours_after"] <= request["hours"]["contract_hours"]
    answer = client.post(
        f"/me/cover-requests/{request['offer_id']}", json={"accept": True}, headers=alvarez
    ).json()
    assert answer == {"status": "closed", "escalation_reason": None}
    assert _shift(client, alvarez, "2026-10-20", "frueh")["changed"]
    overview = client.get("/planner/overview", headers=brandt).json()
    assert any(
        x["kind"] == "cover"
        and x["date"] == "2026-10-20"
        and x["approval"] == "policy"
        and x["staff_name"] == "Dr. Sofía Alvarez"
        for x in overview["recent"]
    )
