"""C1 and C2 behind the screens: the M5 trade-off, published-roster changes, the arq queue."""

import asyncio
import os
import uuid
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dienstpilot.app.deps import get_engines
from dienstpilot.engines.built import CpSatOptimizer
from dienstpilot_solver.model import Config, Problem, Result

from .helpers import coverable_shift

pytestmark = pytest.mark.db
LEAVE = {"start_date": "2027-01-04", "end_date": "2027-01-17"}


def _check(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    started = client.post("/me/leave/check", json=LEAVE, headers=h).json()
    r = client.get(f"/me/leave/checks/{started['trade_off_check_id']}", headers=h).json()
    assert r["status"] == "done" and r["engine"]["component"] == "C1", r
    return dict(r)


def test_a_single_leave_in_january_is_coverable_without_a_trade(
    client: TestClient, login: Any
) -> None:
    """With the real solver: absorbed without extra overtime or peak burden."""
    r = _check(client, login("kaya"))["result"]
    assert r["outcome"] == "coverable" and r["trade_off"] is None
    assert set(r["impact"]) == {"overtime_hours_delta", "peak_burden_delta"}
    assert r["thresholds"] == {"overtime_hours": 8.0, "peak_burden": 2}


class LeaveCostsOvertime(CpSatOptimizer):
    """Test only: the real solver, but covering ``staff_id``'s leave is reported as +12 h overtime.

    The synthetic department absorbs one leave without overtime, so the trade-off branch is
    driven here; everything else (the earlier month, the weekend commitment, C2) is real.
    """

    def __init__(self, staff_id: str) -> None:
        self.staff_id = staff_id

    def solve(self, problem: Problem, config: Config) -> Result:
        result = super().solve(problem, config)
        if result.status != "ok" or not problem.leave.get(self.staff_id):
            return result
        if problem.month != date(2027, 1, 1):
            return result
        v = result.variants[0]
        heavier = replace(v.metrics, overtime_hours=v.metrics.overtime_hours + 12)
        return replace(result, variants=(replace(v, metrics=heavier),))


def _weekends(row: dict[str, Any]) -> int:
    days = [date.fromisoformat(d) for d, c in row["cells"].items() if c["shifts"]]
    return len({d - timedelta(days=d.weekday() - 5) for d in days if d.weekday() >= 5})


def test_trade_off_is_offered_committed_and_binds_the_earlier_month(
    app_factory: Any, client: TestClient, login: Any
) -> None:
    brandt = login("brandt")
    reasons = []
    for persona in ("kaya", "mehta", "weber", "alvarez", "nowak"):
        kaya = login(persona)
        kaya_id = client.get("/me", headers=kaya).json()["staff_id"]
        app_factory.queue.engines = replace(get_engines(), optimizer=LeaveCostsOvertime(kaya_id))
        check = _check(client, kaya)
        r = check["result"]
        if r["outcome"] == "coverable_with_trade_off":
            break
        # (a): no trade-off if the extra weekend would break a hard rule in December.
        assert r["outcome"] == "coverable" and r["reason"] == "weekend_limit", r
        reasons.append(r["reason"])
    else:
        pytest.skip(f"every demo persona is at the December weekend limit: {reasons}")
    assert r["impact"]["overtime_hours_delta"] > r["thresholds"]["overtime_hours"]
    trade = r["trade_off"]
    assert trade["month"] == "2026-12-01" and 1 <= trade["weekends"] <= 2

    # Without a check id, or with other dates, there is no trade.
    assert (
        client.post("/me/leave", json={**LEAVE, "with_trade": True}, headers=kaya).status_code
        == 422
    )
    created = client.post(
        "/me/leave", json={**LEAVE, "with_trade": True, "check_id": check["id"]}, headers=kaya
    )
    assert (
        created.status_code == 201 and created.json()["trade_off"]["weekends"] == trade["weekends"]
    )
    ok = client.post(
        f"/planner/leave/{created.json()['id']}/decision", json={"approve": True}, headers=brandt
    )
    assert ok.json()["status"] == "approved"

    # Planning December now has to keep the promise in every variant.
    app_factory.queue.engines = None
    queued = client.post("/planner/runs", json={"roster_month": "2026-12"}, headers=brandt).json()
    run = client.get(f"/planner/runs/{queued['run_id']}", headers=brandt).json()
    assert run["status"] == "done"
    for v in run["variants"]:
        grid = client.get(
            f"/roster?month=2026-12&variant_id={v['variant_id']}", headers=brandt
        ).json()
        row = next(x for x in grid["rows"] if x["staff_id"] == kaya_id)
        assert _weekends(row) >= trade["weekends"], v["label"]


def test_published_change_needs_a_reason_passes_c2_and_notifies_both(
    client: TestClient, login: Any
) -> None:
    brandt, mehta = login("brandt"), login("nowak")
    shift = coverable_shift(client, mehta, free_to_give=True)
    change = {"assignment_id": shift["assignment_id"]}
    no_reason = client.patch("/planner/roster/assignments", json=change, headers=brandt)
    assert no_reason.status_code == 422
    rows = client.get(f"/roster?month={shift['date'][:7]}", headers=brandt).json()["rows"]
    mehta_id = client.get("/me", headers=mehta).json()["staff_id"]
    reason = "Fortbildung am Vormittag"
    refused = done = None
    for row in rows:
        if row["staff_id"] == mehta_id:
            continue
        r = client.patch(
            "/planner/roster/assignments",
            json={**change, "new_staff_id": row["staff_id"], "reason": reason},
            headers=brandt,
        )
        if r.status_code == 422 and refused is None:
            refused = r.json()["detail"]
        if r.status_code == 200:
            done = (row, r.json())
            break
    assert refused is not None and refused["code"] == "rule_violation"
    assert all(v["key"].startswith("violation.") for v in refused["violations"])
    assert done is not None, "C2 should allow at least one colleague (the shift is coverable)"
    row, out = done
    assert sorted(out["notified"]) == sorted([mehta_id, row["staff_id"]])
    notes = client.get("/me/notifications", headers=mehta).json()
    assert any(n["kind"] == "roster_changed" and n["data"]["reason"] == reason for n in notes)
    roster = client.get(f"/roster?month={shift['date'][:7]}", headers=brandt).json()
    new_row = next(x for x in roster["rows"] if x["staff_id"] == row["staff_id"])
    assert new_row["cells"][shift["date"]]["changed"]
    events = client.get(
        "/audit/events?action=roster.changed&since=2026-10-20T00:00:00%2B02:00", headers=brandt
    ).json()["events"]
    assert len(events) == 2 and all(e["payload"]["reason"] == reason for e in events)


def test_hours_carry_rest_compliance_from_c2(client: TestClient, login: Any) -> None:
    h = client.get("/me/hours?month=2026-11", headers=login("kaya")).json()
    rest = h["rest_compliance"]
    assert rest["validator"]["component"] == "C2" and rest["compliant"] == (rest["violations"] == 0)
    report = client.get("/compliance/hours?month=2026-10", headers=login("vogel")).json()
    assert report["rest_violations_total"] == sum(
        p["rest_compliance"]["violations"] for p in report["people"]
    )


@pytest.mark.skipif(not os.environ.get("TEST_REDIS_URL"), reason="TEST_REDIS_URL not set")
def test_arq_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real queue: ArqQueue enqueues, a burst worker runs the job with the arguments."""
    from arq.worker import Worker

    from dienstpilot import worker
    from dienstpilot.app.queue import ArqQueue

    url = os.environ["TEST_REDIS_URL"]
    calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(worker, "_run", lambda name, kwargs: calls.append((name, kwargs)))
    queue = "dienstpilot:test-jobs"
    run_id = f"r-{uuid.uuid4()}"  # job ids are unique; arq keeps results for a while
    ArqQueue(url, queue).enqueue("run_roster", run_id=run_id, department_id="d-test")

    async def burst() -> None:
        w = Worker(
            functions=worker.WorkerSettings.functions,
            redis_settings=ArqQueue(url)._settings,
            queue_name=queue,
            burst=True,
            poll_delay=0.05,
        )
        await w.main()
        await w.close()

    asyncio.run(burst())
    assert calls == [("run_roster", {"run_id": run_id, "department_id": "d-test"})]
