"""The C8 task suite and its ground truth against the seeded database, and the history tool."""

import json
from pathlib import Path
from typing import Any

import c8_tasks
import pytest
from c8_harness import World
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db
SUITE = Path(__file__).resolve().parents[3] / "eval" / "c8_tasks.json"


def test_committed_tasks_equal_what_the_seed_and_the_sql_give(
    client: TestClient, app_factory: Any
) -> None:
    w = World(app_factory.conn, client, None)
    fresh = c8_tasks.assemble(w)
    committed = json.loads(SUITE.read_text())
    assert fresh == committed, "eval/c8_tasks.json is stale: run uv run python eval/c8_tasks.py"


def test_split_is_stratified_and_recorded() -> None:
    suite = json.loads(SUITE.read_text())
    by = {(t["kind"], t["split"]): 0 for t in suite["tasks"]}
    for t in suite["tasks"]:
        by[(t["kind"], t["split"])] += 1
    for kind, (n_dev, n_test) in c8_tasks.SPLIT.items():
        assert (by[(kind, "dev")], by[(kind, "test")]) == (n_dev, n_test)
    assert len(suite["split"]["dev"]) == 20 and len(suite["split"]["test"]) == 30
    assert not set(suite["split"]["dev"]) & set(suite["split"]["test"])


def test_history_is_for_the_planner_only_and_shows_proposals(
    client: TestClient, login: Any
) -> None:
    planner = login("brandt")
    made = client.post(
        "/copilot/proposals",
        headers=planner,
        json={"title": "Ankündigung: Test", "body": "Text", "kind": "announcement"},
    )
    assert made.status_code == 201
    r = client.get("/planner/history?month=2026-11", headers=planner)
    assert r.status_code == 200
    assert any(p["title"] == "Ankündigung: Test" for p in r.json()["proposals"])
    assert client.get("/planner/history?month=2026-11", headers=login("vogel")).status_code == 403
    assert client.get("/planner/history?month=2026-11", headers=login("kaya")).status_code == 403
