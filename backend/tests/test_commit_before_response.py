"""A write is committed before the client gets its response (no read-after-write race)."""

import asyncio
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI

from dienstpilot.app.deps import SessionDep
from dienstpilot.shared.database import get_session


def test_the_session_commits_before_the_response_is_sent() -> None:
    events: list[str] = []

    def fake_session() -> Iterator[object]:
        yield object()
        events.append("commit")  # what get_session does after the handler

    app = FastAPI()
    app.dependency_overrides[get_session] = fake_session

    @app.post("/write")
    def write(_: SessionDep) -> dict[str, bool]:
        events.append("handler")
        return {"ok": True}

    async def call() -> None:
        sent = False

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                events.append("response sent")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/write",
            "raw_path": b"/write",
            "query_string": b"",
            "headers": [],
            "server": ("test", 80),
            "client": ("test", 1),
            "scheme": "http",
        }
        await app(scope, receive, send)  # type: ignore[arg-type]

    asyncio.run(call())
    assert events == ["handler", "commit", "response sent"]
