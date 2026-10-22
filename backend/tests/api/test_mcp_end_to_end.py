"""MCP tools against the real API and database (through the API's own TestClient)."""

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

import anyio
import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text

from dienstpilot.app.routes.rules import get_embedder
from dienstpilot_agents.rag import vectors
from dienstpilot_mcp.app import create_app
from dienstpilot_mcp.backend_client import Backend

from .helpers import coverable_shift

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Bridge(httpx.AsyncBaseTransport):
    """Sends the MCP server's REST calls into the API's TestClient (same database session)."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        def call() -> Any:
            return self.client.request(
                request.method,
                request.url.raw_path.decode(),
                content=request.content,
                headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            )

        r = await anyio.to_thread.run_sync(call)
        return httpx.Response(r.status_code, headers=r.headers, content=r.content)


@contextlib.asynccontextmanager
async def mcp(client: TestClient) -> AsyncIterator[Any]:
    app = create_app(Backend("http://api", transport=Bridge(client)), allowed_hosts=["mcp"])
    async with app.router.lifespan_context(app):
        yield app


def connect(app: Any, server: str, token: str) -> Any:
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://mcp",
        headers={"authorization": f"Bearer {token}"},
    )
    return Client(streamable_http_client(f"http://mcp/{server}/mcp", http_client=http))


def token(client: TestClient, persona: str) -> str:
    return str(client.post("/auth/demo-login", json={"persona": persona}).json()["access_token"])


def names(app_factory: Any) -> set[str]:
    rows = app_factory.conn.execute(text("SELECT display_name FROM organization.staff")).scalars()
    out: set[str] = set()
    for n in rows:
        out.add(n)
        out.add(n.split()[-1])
    return out


async def test_planner_reads_roster_and_burden_without_any_name(
    client: TestClient, app_factory: Any
) -> None:
    async with mcp(client) as app:
        t = token(client, "brandt")
        outputs = []
        async with connect(app, "roster", t) as c:
            outputs.append(await c.call_tool("get_roster", {"month": "2026-11"}))
            outputs.append(await c.call_tool("get_coverage", {"month": "2026-11"}))
            outputs.append(await c.call_tool("get_burden_ledger", {}))
        dump = json.dumps([o.structured_content for o in outputs], ensure_ascii=False)
        assert not [n for n in names(app_factory) if n in dump], "a name left the server"
        assert "category" not in dump and "sick" not in dump
        roster = outputs[0].structured_content
        assert roster["status"] == "published" and roster["rows"]  # type: ignore[index]
        assert outputs[2].structured_content["people"]  # type: ignore[index]


async def test_oversight_gets_statistics_but_no_person_level_burden(client: TestClient) -> None:
    async with mcp(client) as app:
        async with connect(app, "roster", token(client, "vogel")) as c:
            r = await c.call_tool("get_burden_ledger", {})
        assert r.structured_content["people"] is None  # type: ignore[index]


async def test_what_if_and_candidates_match_the_api(
    client: TestClient, login: Any, app_factory: Any
) -> None:
    shift = coverable_shift(client, login("weber"))
    async with mcp(client) as app:
        t = token(client, "brandt")
        async with connect(app, "forecast", t) as c:
            cands = await c.call_tool(
                "get_cover_candidates", {"assignment_id": shift["assignment_id"]}
            )
            fc = await c.call_tool("get_absence_forecast", {"days": 7})
        ids = cands.structured_content["candidates"]  # type: ignore[index]
        assert ids and len(fc.structured_content["days"]) == 7  # type: ignore[index]
        async with connect(app, "planning", t) as c:
            wi = await c.call_tool(
                "run_what_if",
                {"changes": [{"assignment_id": shift["assignment_id"], "new_staff_id": ids[0]}]},
            )
        # A candidate the validator already cleared for this shift brings no violation of their own.
        sc = wi.structured_content
        assert all(v["staff_id"] != ids[0] for v in sc["introduced"]), sc  # type: ignore[index]
        dump = json.dumps(wi.structured_content, ensure_ascii=False)
        assert not [n for n in names(app_factory) if n in dump]


async def test_rules_search_through_mcp_has_citations(client: TestClient) -> None:
    import json as _json
    from pathlib import Path

    qs = _json.loads((Path(__file__).resolve().parents[3] / "eval/rag_questions.json").read_text())
    emb = vectors.load("questions", [q["question"] for q in qs["questions"]]).embedder()
    client.app.dependency_overrides[get_embedder] = lambda: emb  # type: ignore[attr-defined]
    q = next(x for x in qs["questions"] if x["id"] == "rest-de")["question"]
    async with mcp(client) as app, connect(app, "rules", token(client, "vogel")) as c:
        r = await c.call_tool("search_rules", {"query": q})
        one = await c.call_tool("get_rule", {"rule_id": "arbzg:§5:1"})
    assert (r.structured_content["mode"], r.structured_content["fallback"]) == ("vector", False)  # type: ignore[index]
    assert r.structured_content["found"] is True  # type: ignore[index]
    assert any(p["id"] == "arbzg:§5:1" for p in r.structured_content["passages"])  # type: ignore[index]
    assert one.structured_content["citation"].startswith("Arbeitszeitgesetz")  # type: ignore[index]


async def test_proposals_are_the_only_write_and_the_roster_is_untouched(
    client: TestClient, app_factory: Any
) -> None:
    conn = app_factory.conn

    def snapshot() -> tuple[int, int]:
        return (
            conn.execute(text("SELECT count(*) FROM planning.assignment_change")).scalar_one(),
            conn.execute(text("SELECT count(*) FROM planning.approval")).scalar_one(),
        )

    before = snapshot()
    async with mcp(client) as app:
        t = token(client, "brandt")
        async with connect(app, "planning", t) as c:
            r = await c.call_tool("create_proposal", {"title": "Idee", "body": "Text"})
        async with connect(app, "notify", t) as c:
            d = await c.call_tool(
                "draft_announcement", {"audience": "Assistenzärzte", "title": "T", "text": "Hallo"}
            )
    assert (
        r.structured_content["kind"] == "change" and d.structured_content["kind"] == "announcement"
    )  # type: ignore[index]
    kinds = conn.execute(
        text("SELECT kind, source, status FROM planning.proposal ORDER BY created_at")
    ).all()
    assert {(k, s, st) for k, s, st in kinds if st == "open"} >= {
        ("change", "copilot", "open"),
        ("announcement", "copilot", "open"),
    }
    assert snapshot() == before


async def test_search_rules_reports_the_fallback_when_the_model_is_missing(
    client: TestClient,
) -> None:
    client.app.dependency_overrides[get_embedder] = lambda: None  # type: ignore[attr-defined]
    async with mcp(client) as app, connect(app, "rules", token(client, "brandt")) as c:
        r = await c.call_tool("search_rules", {"query": "Ruhezeit Stunden"})
    sc = r.structured_content
    assert (sc["mode"], sc["configured"], sc["fallback"]) == ("fts-only", "vector", True)  # type: ignore[index]
    assert sc["passages"], "full-text still finds passages"  # type: ignore[index]
