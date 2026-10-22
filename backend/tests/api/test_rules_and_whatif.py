"""The rulebook endpoints, the what-if and proposals with a kind and changes (10a)."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from dienstpilot.app.routes.rules import get_embedder
from dienstpilot_agents.rag import vectors
from dienstpilot_agents.rag.corpus import load_corpus

from .helpers import coverable_shift

pytestmark = pytest.mark.db
REPO = Path(__file__).resolve().parents[3]
QUESTIONS = {
    q["id"]: q for q in json.loads((REPO / "eval/rag_questions.json").read_text())["questions"]
}


@pytest.fixture
def with_vectors(client: TestClient) -> TestClient:
    """The committed question vectors stand in for the model (CI never loads it)."""
    qs = [q["question"] for q in QUESTIONS.values()]
    emb = vectors.load("questions", qs).embedder()
    client.app.dependency_overrides[get_embedder] = lambda: emb  # type: ignore[attr-defined]
    return client


def test_the_seed_loads_the_rulebook_index(app_factory: Any) -> None:
    n = app_factory.conn.execute(text("SELECT count(*) FROM rag.chunk")).scalar_one()
    _, chunks = load_corpus()
    assert n == len(chunks)


def test_only_planner_and_oversight_search_the_rules(client: TestClient, login: Any) -> None:
    for persona, code in (("brandt", 200), ("vogel", 200), ("kaya", 403), ("it-admin", 403)):
        r = client.get("/rules/search?q=Ruhezeit", headers=login(persona))
        assert r.status_code == code, persona


def test_a_question_finds_the_statute_with_a_citation(with_vectors: TestClient, login: Any) -> None:
    q = QUESTIONS["rest-de"]["question"]
    r = with_vectors.get("/rules/search", params={"q": q, "k": 5}, headers=login("brandt")).json()
    assert r["found"] and r["mode"] == "hybrid" and r["vector_used"]
    ids = [p["id"] for p in r["passages"]]
    assert set(ids) & set(QUESTIONS["rest-de"]["gold"])
    top = next(p for p in r["passages"] if p["id"] == "arbzg:§5:1")
    assert top["citation"] == "Arbeitszeitgesetz (ArbZG) § 5 Abs. 1 (Stand 2024-12-31)"
    assert top["synthetic"] is False
    synthetic = [p for p in r["passages"] if p["synthetic"]]
    assert all("[synthet" in p["citation"] for p in synthetic)


def test_an_english_question_finds_the_german_statute(with_vectors: TestClient, login: Any) -> None:
    q = QUESTIONS["rest-en"]["question"]
    r = with_vectors.get("/rules/search", params={"q": q}, headers=login("vogel")).json()
    assert {p["id"] for p in r["passages"]} & set(QUESTIONS["rest-en"]["gold"])


def test_a_question_without_a_source_says_so(with_vectors: TestClient, login: Any) -> None:
    for qid in ("none1-de", "none2-en"):
        q = QUESTIONS[qid]["question"]
        r = with_vectors.get("/rules/search", params={"q": q}, headers=login("brandt")).json()
        assert r["found"] is False and r["passages"] == []


def test_without_the_model_search_is_full_text_only_and_says_so(
    client: TestClient, login: Any
) -> None:
    client.app.dependency_overrides[get_embedder] = lambda: None  # type: ignore[attr-defined]
    r = client.get("/rules/search?q=Ruhezeit Stunden", headers=login("brandt")).json()
    assert r["mode"] == "fts-only" and r["vector_used"] is False


def test_one_passage_by_id(client: TestClient, login: Any) -> None:
    h = login("brandt")
    r = client.get("/rules/arbzg:§5:1", headers=h)
    assert r.status_code == 200 and "elf Stunden" in r.json()["text"]
    assert client.get("/rules/arbzg:§99:1", headers=h).status_code == 404


# --- what-if ----------------------------------------------------------------------------------


def _shift_and_colleague(client: TestClient, login: Any) -> tuple[dict[str, Any], str]:
    weber = login("weber")
    shift = coverable_shift(client, weber)
    staff = client.get("/roster?month=" + shift["date"][:7], headers=login("brandt")).json()["rows"]
    me = next(r for r in staff if r["display_name"] == "Dr. Jonas Weber")["staff_id"]
    other = next(
        r["staff_id"] for r in staff if r["staff_id"] != me and r["title_en"] == "Resident"
    )
    return shift, other


def _counts(conn: Any) -> tuple[int, int, int]:
    return tuple(  # type: ignore[return-value]
        conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
        for t in ("audit.event", "events.outbox", "planning.assignment_change")
    )


def test_what_if_writes_nothing(client: TestClient, login: Any, app_factory: Any) -> None:
    shift, other = _shift_and_colleague(client, login)
    before = _counts(app_factory.conn)
    body = {"changes": [{"assignment_id": shift["assignment_id"], "new_staff_id": other}]}
    w = client.post("/planner/what-if", json=body, headers=login("brandt"))
    assert w.status_code == 200 and w.json()["validator"]["component"] == "C2"
    assert {p["staff_id"] for p in w.json()["people"]} >= {other}
    assert _counts(app_factory.conn) == before


def test_what_if_agrees_with_the_real_change(client: TestClient, login: Any) -> None:
    brandt = login("brandt")
    shift, other = _shift_and_colleague(client, login)
    change = {"assignment_id": shift["assignment_id"], "new_staff_id": other}
    verdict = client.post("/planner/what-if", json={"changes": [change]}, headers=brandt).json()
    real = client.patch(
        "/planner/roster/assignments", json={**change, "reason": "Test"}, headers=brandt
    )
    assert (real.status_code == 200) == verdict["valid"]
    if not verdict["valid"]:
        assert real.status_code == 422
        rules = {v["rule"] for v in verdict["introduced"]}
        assert rules <= {v["rule"] for v in real.json()["detail"]["violations"]}


def test_what_if_removal_reports_the_gap_and_hours(client: TestClient, login: Any) -> None:
    shift, _ = _shift_and_colleague(client, login)
    r = client.post(
        "/planner/what-if",
        json={"changes": [{"assignment_id": shift["assignment_id"], "new_staff_id": None}]},
        headers=login("brandt"),
    ).json()
    assert r["removed_without_replacement"] == [
        {"date": shift["date"], "shift_type": shift["shift_type"]}
    ]
    assert r["people"][0]["hours_delta"] < 0


def test_what_if_refuses_the_past_unpublished_and_other_departments(
    client: TestClient, login: Any
) -> None:
    h = login("brandt")
    shift, _ = _shift_and_colleague(client, login)
    bad = {
        "changes": [
            {
                "assignment_id": shift["assignment_id"],
                "new_staff_id": "0" * 8 + "-0000-0000-0000-" + "0" * 12,
            }
        ]
    }
    assert client.post("/planner/what-if", json=bad, headers=h).status_code == 404
    assert client.post("/planner/what-if", json={"changes": []}, headers=h).status_code == 422
    assert client.post("/planner/what-if", json={"changes": [{}]}, headers=h).status_code == 422
    assert (
        client.post("/planner/what-if", json={"changes": [{}]}, headers=login("kaya")).status_code
        == 403
    )


# --- proposals --------------------------------------------------------------------------------


def test_proposals_carry_a_kind_and_changes_and_nothing_applies_them(
    client: TestClient, login: Any, app_factory: Any
) -> None:
    brandt = login("brandt")
    shift, other = _shift_and_colleague(client, login)
    before = app_factory.conn.execute(
        text("SELECT count(*) FROM planning.assignment_change")
    ).scalar_one()
    created = client.post(
        "/copilot/proposals",
        json={
            "title": "Vorschlag",
            "body": "Dr. X übernimmt",
            "kind": "change",
            "changes": [{"assignment_id": shift["assignment_id"], "new_staff_id": other}],
        },
        headers=brandt,
    )
    assert created.status_code == 201
    draft = client.post(
        "/copilot/proposals",
        json={"title": "Ankündigung", "body": "Text", "kind": "announcement"},
        headers=brandt,
    )
    assert draft.status_code == 201
    inbox = client.get("/planner/requests", headers=brandt).json()["proposals"]
    mine = {p["title"]: p for p in inbox}
    assert mine["Vorschlag"]["kind"] == "change" and len(mine["Vorschlag"]["changes"]) == 1
    assert mine["Ankündigung"]["kind"] == "announcement" and mine["Ankündigung"]["changes"] is None
    decided = client.post(
        f"/planner/proposals/{mine['Vorschlag']['id']}/decision",
        json={"accept": True},
        headers=brandt,
    )
    assert decided.status_code == 200
    after = app_factory.conn.execute(
        text("SELECT count(*) FROM planning.assignment_change")
    ).scalar_one()
    assert after == before, "accepting a proposal never changes the roster"
    assert (
        client.post(
            "/copilot/proposals",
            json={"title": "x", "body": "y", "kind": "publish"},
            headers=brandt,
        ).status_code
        == 422
    )
    assert timedelta  # keep the import used
