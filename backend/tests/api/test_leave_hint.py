"""C6 on M5: the hint is advisory, the solver's answer wins, and every disagreement is logged."""

from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from dienstpilot.app.deps import get_engines
from dienstpilot.app.jobs import hint_agreement
from dienstpilot.shared.ports import EngineInfo, LeaveFacts, LeaveFeasibility, LeaveHint

pytestmark = pytest.mark.db
KAYA = {"start_date": "2027-07-14", "end_date": "2027-07-27"}


class FixedHint(LeaveFeasibility):
    """A hint engine that always says the same thing (tests only)."""

    info = EngineInfo("C6", "built", "test-fixed", "A fixed hint for a test.", None)

    def __init__(self, outcome: str) -> None:
        self.outcome = outcome

    def hint(self, facts: LeaveFacts, limit: int) -> LeaveHint:
        return LeaveHint(self.outcome, 0, limit, facts.overlapping)  # type: ignore[arg-type]


def test_agreement_table() -> None:
    cases = {
        ("coverable", "coverable"): "agree",
        ("coverable", "coverable_with_trade_off"): "disagree",
        ("coverable", "not_coverable"): "disagree",
        ("not_coverable", "coverable"): "disagree",
        ("not_coverable", "coverable_with_trade_off"): "agree",
        ("not_coverable", "not_coverable"): "agree",
        ("tight", "coverable"): "abstain",
        ("tight", "not_coverable"): "abstain",
        ("coverable", "not_applicable"): "not_scored",
        (None, "coverable"): "not_scored",
    }
    for (hint, solver), expected in cases.items():
        assert hint_agreement(hint, solver) == expected, (hint, solver)


def _stored(app_factory: Any, check_id: str) -> Any:
    row = app_factory.conn.execute(
        text(
            "SELECT hint_outcome, hint_version, hint_basis, agreement "
            "FROM requests.leave_check WHERE id = :i"
        ),
        {"i": check_id},
    ).one()
    return row


@pytest.mark.production_solver
def test_a_wrong_hint_loses_to_the_solver_and_the_disagreement_is_logged(
    app_factory: Any, client: TestClient, login: Any
) -> None:
    """Situation A keeps its honest result whatever the hint says (nothing is tuned to agree)."""
    engines = replace(get_engines(), leave=FixedHint("not_coverable"))
    client.app.dependency_overrides[get_engines] = lambda: engines  # type: ignore[attr-defined]
    kaya = login("kaya")
    hint = client.post("/me/leave/check", json=KAYA, headers=kaya).json()
    assert hint["outcome"] == "not_coverable"
    check = client.get(f"/me/leave/checks/{hint['trade_off_check_id']}", headers=kaya).json()
    assert check["status"] == "done"
    assert check["result"]["outcome"] == "coverable" and check["result"]["trade_off"] is None
    stored = _stored(app_factory, hint["trade_off_check_id"])
    assert tuple(stored) == ("not_coverable", "test-fixed", "model", "disagree")
    events = client.get("/audit/events?action=leave.hint_disagreed", headers=login("brandt"))
    rows = events.json()["events"]
    assert any(e["subject_id"] == hint["trade_off_check_id"] for e in rows)
    e = next(e for e in rows if e["subject_id"] == hint["trade_off_check_id"])
    assert e["payload"]["hint"] == "not_coverable" and e["payload"]["solver"] == "coverable"
    assert e["staff_name"] is None  # no name in the log


@pytest.mark.production_solver
def test_an_agreeing_hint_is_not_logged(app_factory: Any, client: TestClient, login: Any) -> None:
    engines = replace(get_engines(), leave=FixedHint("coverable"))
    client.app.dependency_overrides[get_engines] = lambda: engines  # type: ignore[attr-defined]
    kaya = login("kaya")
    hint = client.post("/me/leave/check", json=KAYA, headers=kaya).json()
    client.get(f"/me/leave/checks/{hint['trade_off_check_id']}", headers=kaya)
    assert _stored(app_factory, hint["trade_off_check_id"]).agreement == "agree"
    rows = client.get("/audit/events?action=leave.hint_disagreed", headers=login("brandt"))
    assert not any(e["subject_id"] == hint["trade_off_check_id"] for e in rows.json()["events"])


def test_the_served_hint_is_c6_and_stored_with_its_version(
    app_factory: Any, client: TestClient, login: Any
) -> None:
    kaya = login("kaya")
    hint = client.post("/me/leave/check", json=KAYA, headers=kaya).json()
    assert hint["engine"]["component"] == "C6" and hint["engine"]["implementation"] == "built"
    assert hint["outcome"] in ("coverable", "tight", "not_coverable")
    stored = _stored(app_factory, hint["trade_off_check_id"])
    assert stored.hint_outcome == hint["outcome"]
    assert stored.hint_version == hint["engine"]["version"]
    assert stored.hint_basis in ("model", "rule")


def test_a_leave_over_two_months_gets_the_rule_not_the_model(
    app_factory: Any, client: TestClient, login: Any
) -> None:
    hint = client.post(
        "/me/leave/check",
        json={"start_date": "2027-07-26", "end_date": "2027-08-06"},
        headers=login("kaya"),
    ).json()
    assert _stored(app_factory, hint["trade_off_check_id"]).hint_basis == "rule"


class _NoQueue:
    """Takes jobs and does nothing: the latency of the endpoint itself, without the solver."""

    def enqueue(self, job: str, **kwargs: str) -> None:
        return None


def test_endpoint_latency_is_measured_without_the_solver(client: TestClient, login: Any) -> None:
    """``POST /me/leave/check`` end to end (auth, queries, facts, hint, one insert), no solver.

    Reported next to the full hint path in eval/results/c6.json; not a promotion gate. Run with
    ``C6_WRITE_LATENCY=1`` (make eval does) to write eval/results/c6_endpoint_latency.json.
    """
    import json
    import os
    import platform
    import time
    from pathlib import Path

    import numpy as np

    from dienstpilot.app.queue import get_queue

    client.app.dependency_overrides[get_queue] = lambda: _NoQueue()  # type: ignore[attr-defined]
    kaya = login("kaya")
    windows = [
        ("2027-07-14", "2027-07-27"),
        ("2027-03-01", "2027-03-05"),
        ("2027-09-13", "2027-09-24"),
        ("2027-02-08", "2027-02-19"),
    ]
    ms: list[float] = []
    for i in range(45):
        a, b = windows[i % len(windows)]
        t0 = time.perf_counter()
        r = client.post("/me/leave/check", json={"start_date": a, "end_date": b}, headers=kaya)
        dt = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200, r.text
        if i >= 5:  # warm-up
            ms.append(dt)
    doc = {
        "calls": len(ms),
        "warmup_calls": 5,
        "p50_ms": float(np.percentile(ms, 50)),
        "p95_ms": float(np.percentile(ms, 95)),
        "max_ms": float(max(ms)),
        "what": "POST /me/leave/check through the test client, no network, solver not run, "
        "Postgres on the same machine",
        "platform": platform.platform(),
    }
    assert doc["p95_ms"] < 2000  # a sanity bound, not the 50 ms of the hint path
    if os.environ.get("C6_WRITE_LATENCY"):
        out = Path(__file__).resolve().parents[3] / "eval" / "results" / "c6_endpoint_latency.json"
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
