"""The MCP servers: role-scoped tool lists, annotations, schemas, token pass-through, privacy."""

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import httpx2
import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

import fake_api
from dienstpilot_mcp.app import create_app
from dienstpilot_mcp.backend_client import Backend
from dienstpilot_mcp.servers import FORBIDDEN_NAMES, build

pytestmark = pytest.mark.anyio
SERVERS = ["roster", "planning", "rules", "forecast", "notify"]
WRITERS = {"create_proposal", "draft_announcement"}


@contextlib.asynccontextmanager
async def running() -> AsyncIterator[Any]:
    """The MCP app on top of the fake API, served in-process."""
    backend = Backend("http://api", transport=httpx.ASGITransport(app=fake_api.make()))
    app = create_app(backend, allowed_hosts=["mcp"])
    fake_api.CALLS.clear()
    async with app.router.lifespan_context(app):
        yield app


def http(app: Any, token: str | None) -> httpx2.AsyncClient:
    """An HTTP client on the app with an optional bearer token."""
    headers = {} if token is None else {"authorization": f"Bearer {token}"}
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://mcp", headers=headers
    )


async def tools_of(app: Any, server: str, token: str) -> dict[str, Any]:
    """Connect as the token's user and return the listed tools by name."""
    async with Client(
        streamable_http_client(f"http://mcp/{server}/mcp", http_client=http(app, token))
    ) as c:
        return {t.name: t for t in (await c.list_tools()).tools}


async def test_planner_sees_every_tool_oversight_only_reads() -> None:
    async with running() as app:
        planner = {s: await tools_of(app, s, "tok-planner") for s in SERVERS}
        assert {n for s in planner.values() for n in s} == {
            "get_roster", "get_assignments_for", "get_burden_ledger", "get_coverage",
            "run_what_if", "validate", "get_variants", "create_proposal",
            "search_rules", "get_rule", "get_absence_forecast", "get_cover_candidates",
            "draft_announcement",
        }  # fmt: skip
        for server in ("roster", "rules"):
            ov = await tools_of(app, server, "tok-oversight")
            assert ov and all(t.annotations.read_only_hint for t in ov.values())
        ov_planning = await tools_of(app, "planning", "tok-oversight")
        assert set(ov_planning) == {"run_what_if"}  # reads only; no proposal, no validate of drafts


async def test_oversight_has_nothing_on_the_servers_that_write() -> None:
    async with running() as app:
        for server in ("notify", "forecast"):
            r = await http(app, "tok-oversight").post(f"/{server}/mcp", json={})
            assert r.status_code == 403


async def test_no_token_a_bad_token_and_staff_are_refused() -> None:
    async with running() as app:
        assert (await http(app, None).post("/roster/mcp", json={})).status_code == 401
        assert (await http(app, "nope").post("/roster/mcp", json={})).status_code == 401
        assert (await http(app, "tok-staff").post("/roster/mcp", json={})).status_code == 403


async def test_every_tool_is_annotated_typed_and_cannot_publish_or_approve() -> None:
    specs = build(Backend("http://api"))
    names = [s.name for tools in specs.values() for s in tools]
    assert len(names) == len(set(names)) == 13
    assert not [n for n in names if FORBIDDEN_NAMES.search(n)]
    async with running() as app:
        for server in SERVERS:
            for name, tool in (await tools_of(app, server, "tok-planner")).items():
                a = tool.annotations
                assert a is not None and a.destructive_hint is False and a.open_world_hint is False
                assert a.read_only_hint is (name not in WRITERS), name
                assert tool.output_schema, f"{name} has no output schema"
                assert tool.description


async def test_the_callers_own_token_reaches_the_api() -> None:
    async with running() as app:
        async with Client(
            streamable_http_client("http://mcp/roster/mcp", http_client=http(app, "tok-oversight"))
        ) as c:
            await c.call_tool("get_roster", {"month": "2026-11"})
        auth = {a for _, p, a in fake_api.CALLS if p == "/roster"}
        assert auth == {"Bearer tok-oversight"}


async def test_tool_results_carry_ids_only_and_no_absence_category() -> None:
    async with running() as app:
        async with Client(
            streamable_http_client("http://mcp/roster/mcp", http_client=http(app, "tok-planner"))
        ) as c:
            roster = await c.call_tool("get_roster", {"month": "2026-11"})
            burden = await c.call_tool("get_burden_ledger", {})
        dump = json.dumps(
            [roster.structured_content, burden.structured_content], ensure_ascii=False
        )
        assert "Weber" not in dump and "display_name" not in dump and "sick" not in dump
        assert "category" not in dump
        day = roster.structured_content["rows"][0]["days"][0]  # type: ignore[index]
        assert day["absent"] is True and day["shifts"] == ["frueh"]


async def test_what_if_and_rules_results_are_typed_and_without_names() -> None:
    async with running() as app:
        async with Client(
            streamable_http_client("http://mcp/planning/mcp", http_client=http(app, "tok-planner"))
        ) as c:
            r = await c.call_tool(
                "run_what_if", {"changes": [{"assignment_id": "a1", "new_staff_id": fake_api.SID2}]}
            )
        sc = r.structured_content
        assert sc["valid"] is False and sc["introduced"][0]["rule"] == "min_rest"  # type: ignore[index]
        assert "Weber" not in json.dumps(sc) and sc["hours_delta"] == {fake_api.SID: 8.0}  # type: ignore[index]
        async with Client(
            streamable_http_client("http://mcp/rules/mcp", http_client=http(app, "tok-oversight"))
        ) as c:
            s = await c.call_tool("search_rules", {"query": "Ruhezeit Stunden"})
        assert s.structured_content["passages"][0]["citation"].startswith("ArbZG § 5")  # type: ignore[index]


async def test_the_only_writes_are_proposals_and_the_api_decides_who_may() -> None:
    async with running() as app:
        async with Client(
            streamable_http_client("http://mcp/planning/mcp", http_client=http(app, "tok-planner"))
        ) as c:
            r = await c.call_tool("create_proposal", {"title": "t", "body": "b"})
        assert r.structured_content == {"proposal_id": "p1", "status": "open", "kind": "change"}  # type: ignore[comparison-overlap]
        posts = [(m, p) for m, p, _ in fake_api.CALLS if m == "POST"]
        assert posts == [("POST", "/copilot/proposals")]


async def test_an_api_refusal_comes_back_as_a_readable_tool_error() -> None:
    async with running() as app:
        async with Client(
            streamable_http_client("http://mcp/planning/mcp", http_client=http(app, "tok-planner"))
        ) as c:
            r = await c.call_tool("get_variants", {"month": "2026-12"})
        assert r.is_error and "403" in json.dumps([x.model_dump() for x in r.content])
