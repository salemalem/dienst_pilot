"""The C8 world: the real API and the real MCP servers, in process, on a seeded Postgres.

    async with world() as w:
        toolbox = w.toolbox("brandt")            # the agent's tools, as that persona sees them
        rows = w.sql("SELECT ...")               # independent ground truth: plain SQL, no API

Everything runs inside one transaction that is rolled back on exit, so tasks that create a
proposal leave the database as they found it. The demo clock stands still at ``DEMO_NOW``.
Never points at the user's own Postgres on port 5432: only the Docker dev database (5433), or any
database named by ``DATABASE_URL`` that is not on 5432.
"""

import contextlib
import os
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from typing import Any

import anyio
import httpx
import httpx2
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from dienstpilot.app.deps import get_clock
from dienstpilot.app.queue import get_queue
from dienstpilot.main import create_app
from dienstpilot.shared.database import get_session
from dienstpilot.shared.ports import Clock
from dienstpilot.shared.settings import DEMO_NOW, TZ, Settings
from dienstpilot_mcp.app import create_app as create_mcp_app
from dienstpilot_mcp.backend_client import Backend

DEFAULT_URL = "postgresql+psycopg://dienstpilot:dienstpilot@localhost:5433/dienstpilot"


class FixedClock(Clock):
    """The demo clock, standing still."""

    def now(self) -> datetime:
        """Return the demo instant."""
        return DEMO_NOW.astimezone(TZ)


class NoQueue:
    """The C8 world runs no solver jobs."""

    def enqueue(self, job: str, **kwargs: str) -> None:
        """Refuse: an evaluation task must not start a roster run."""
        raise RuntimeError(f"unexpected job {job}")


class Bridge(httpx.AsyncBaseTransport):
    """Sends the MCP server's REST calls into the API's TestClient (same database session)."""

    def __init__(self, client: TestClient) -> None:
        """Remember the in-process API."""
        self.client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Forward one request to the API and return its answer."""

        def call() -> Any:
            return self.client.request(
                request.method,
                request.url.raw_path.decode(),
                content=request.content,
                headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            )

        r = await anyio.to_thread.run_sync(call)
        return httpx.Response(r.status_code, headers=r.headers, content=r.content)


def database_url() -> str:
    """Return the database to use and refuse the user's own Postgres on 5432."""
    url = os.environ.get("C8_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_URL
    if ":5432/" in url or url.endswith(":5432"):
        raise SystemExit("refusing port 5432: that is not the project's Docker database")
    return url


class World:
    """A seeded database, the API on top of it and the MCP servers on top of that."""

    def __init__(self, conn: Connection, client: TestClient, mcp: Any) -> None:
        """Hold the pieces; use ``world()``."""
        self.conn, self.client, self.mcp = conn, client, mcp
        self._tokens: dict[str, str] = {}

    def sql(self, query: str, **params: Any) -> list[Any]:
        """Run read-only SQL: the ground truth never goes through the API."""
        return list(self.conn.execute(text(query), params).all())

    def sql_exec(self, query: str, **params: Any) -> None:
        """Run SQL that writes (planting test data inside the rolled-back transaction)."""
        self.conn.execute(text(query), params)

    def token(self, persona: str) -> str:
        """Return a bearer token for a demo persona."""
        if persona not in self._tokens:
            r = self.client.post("/auth/demo-login", json={"persona": persona})
            r.raise_for_status()
            self._tokens[persona] = str(r.json()["access_token"])
        return self._tokens[persona]

    def mcp_client(self, server: str, persona: str) -> Client:
        """Return an MCP client for one server as one persona."""
        http = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=self.mcp),
            base_url="http://mcp",
            headers={"authorization": f"Bearer {self.token(persona)}"},
        )
        return Client(streamable_http_client(f"http://mcp/{server}/mcp", http_client=http))


@contextlib.asynccontextmanager
async def world() -> AsyncIterator[World]:
    """Open the world; roll everything back when leaving."""
    url = database_url()
    engine = create_engine(url)
    conn = engine.connect()
    outer = conn.begin()

    def session_override() -> Iterator[Session]:
        with Session(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as s:
            yield s
            s.commit()

    app = create_app(Settings(database_url=url))
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_clock] = FixedClock
    app.dependency_overrides[get_queue] = NoQueue
    client = TestClient(app)
    mcp = create_mcp_app(Backend("http://api", transport=Bridge(client)), allowed_hosts=["mcp"])
    try:
        async with mcp.router.lifespan_context(mcp):
            yield World(conn, client, mcp)
    finally:
        outer.rollback()
        conn.close()
        engine.dispose()
