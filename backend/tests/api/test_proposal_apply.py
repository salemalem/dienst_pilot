"""The Planner applies a proposal's changes: validated like a hand edit, all or none."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from .helpers import coverable_shift
from .test_rules_and_whatif import _shift_and_colleague

pytestmark = pytest.mark.db


def _free_shift(client: TestClient, login: Any) -> dict[str, Any]:
    """A future shift someone can take and its holder can give away without breaking a rule."""
    for who in ("kaya", "mehta", "alvarez", "nowak", "lorenz", "schulz", "weber"):
        try:
            return coverable_shift(client, login(who), free_to_give=True)
        except AssertionError:
            continue
    raise AssertionError("no such shift in the seed")


def _changes(conn: Any) -> int:
    return int(conn.execute(text("SELECT count(*) FROM planning.assignment_change")).scalar_one())


def _propose(client: TestClient, h: dict[str, str], changes: list[dict[str, Any]]) -> str:
    r = client.post(
        "/copilot/proposals",
        json={"title": "Tausch vorschlagen", "body": "Text", "changes": changes},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_a_valid_proposal_is_applied_with_a_reason_and_marked_accepted(
    client: TestClient, login: Any, app_factory: Any
) -> None:
    brandt = login("brandt")
    shift = _free_shift(client, login)
    cover = client.get(
        f"/planner/cover-candidates?assignment_id={shift['assignment_id']}", headers=brandt
    ).json()
    assert cover["candidates"], "no colleague that C2 accepts for this shift"
    change = {"assignment_id": shift["assignment_id"], "new_staff_id": cover["candidates"][0]}
    pid = _propose(client, brandt, [change])
    before = _changes(app_factory.conn)
    r = client.post(f"/planner/proposals/{pid}/apply", headers=brandt)
    assert r.status_code == 200 and r.json()["status"] == "accepted", r.text
    assert _changes(app_factory.conn) == before + 1
    reason = app_factory.conn.execute(
        text("SELECT reason FROM planning.assignment_change ORDER BY changed_at DESC LIMIT 1")
    ).scalar_one()
    assert reason == "Vorschlag: Tausch vorschlagen"
    assert client.post(f"/planner/proposals/{pid}/apply", headers=brandt).status_code == 409


def test_a_proposal_that_breaks_a_rule_is_refused_like_a_hand_edit(
    client: TestClient, login: Any, app_factory: Any
) -> None:
    brandt = login("brandt")
    shift, other = _shift_and_colleague(client, login)
    cover = client.get(
        f"/planner/cover-candidates?assignment_id={shift['assignment_id']}", headers=brandt
    ).json()
    rows = client.get("/roster?month=" + shift["date"][:7], headers=brandt).json()["rows"]
    bad = next(
        (
            r["staff_id"]
            for r in rows
            if r["staff_id"] not in cover["candidates"] and r["staff_id"] != other
        ),
        None,
    )
    if bad is None:
        pytest.skip("every colleague is a valid candidate")
    change = {"assignment_id": shift["assignment_id"], "new_staff_id": bad}
    verdict = client.post("/planner/what-if", json={"changes": [change]}, headers=brandt).json()
    pid = _propose(client, brandt, [change])
    before = _changes(app_factory.conn)
    r = client.post(f"/planner/proposals/{pid}/apply", headers=brandt)
    if not verdict["valid"]:
        assert r.status_code == 422 and _changes(app_factory.conn) == before


def test_one_bad_change_undoes_the_others(client: TestClient, login: Any, app_factory: Any) -> None:
    brandt = login("brandt")
    shift, other = _shift_and_colleague(client, login)
    good = {"assignment_id": shift["assignment_id"], "new_staff_id": other}
    bad = {"assignment_id": "00000000-0000-0000-0000-000000000000", "new_staff_id": other}
    pid = _propose(client, brandt, [good, bad])
    before = _changes(app_factory.conn)
    assert client.post(f"/planner/proposals/{pid}/apply", headers=brandt).status_code in (404, 422)
    assert _changes(app_factory.conn) == before


def test_only_the_planner_can_apply_and_a_proposal_without_changes_cannot(
    client: TestClient, login: Any
) -> None:
    brandt = login("brandt")
    pid = _propose(client, brandt, [])
    assert client.post(f"/planner/proposals/{pid}/apply", headers=brandt).status_code == 409
    for who in ("vogel", "kaya"):
        assert client.post(f"/planner/proposals/{pid}/apply", headers=login(who)).status_code == 403
