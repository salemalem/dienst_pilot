"""The ASGI app: five servers at ``/<server>/mcp``, one process (ADR-018).

Every request must carry the demo bearer token. The token is checked by the API itself
(``GET /me``), which also says the role; the role picks the server instance with the tools that
role may use. Mounting only one server makes it an independent deployment.
"""

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

from dienstpilot_mcp.backend_client import Backend, bind, unbind
from dienstpilot_mcp.servers import build, make_server

ROLES = ("planner", "oversight")


async def _reply(send: Send, status: int, message: str) -> None:
    body = json.dumps({"error": message}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RoleGate:
    """Checks the token with the API and hands the request to the server instance of its role."""

    def __init__(self, backend: Backend, apps: dict[str, ASGIApp]) -> None:
        """Remember the backend and one app per role."""
        self._backend, self._apps = backend, apps

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Authenticate, then serve."""
        headers = {k.lower(): v for k, v in scope["headers"]}
        auth = headers.get(b"authorization", b"").decode()
        if not auth.lower().startswith("bearer "):
            await _reply(send, 401, "Bearer token required")
            return
        token = auth.split(" ", 1)[1]
        me = await self._backend.whoami(token)
        if me is None:
            await _reply(send, 401, "Invalid or expired token")
            return
        app = self._apps.get(me["role"])
        if app is None:
            await _reply(send, 403, f"Role {me['role']} has no MCP tools")
            return
        handles = bind(token, me["role"])
        try:
            await app(scope, receive, send)
        finally:
            unbind(handles)


def create_app(
    backend: Backend, only: set[str] | None = None, allowed_hosts: list[str] | None = None
) -> Starlette:
    """Build the app. ``only`` mounts a subset of the servers (independent deployment).

    ``allowed_hosts``: the Host headers accepted (DNS-rebinding protection of the MCP transport);
    the default is the local ones and the compose service name ``mcp``.
    """
    hosts = allowed_hosts or ["localhost", "localhost:*", "127.0.0.1:*", "mcp", "mcp:*"]
    security = TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=[])
    specs = build(backend)
    inner: list[Starlette] = []
    routes: list[Mount] = []
    for name, tools in specs.items():
        if only is not None and name not in only:
            continue
        apps: dict[str, ASGIApp] = {}
        for role in ROLES:
            if not any(role in s.roles for s in tools):
                continue  # this role has no tool on this server
            server = make_server(name, role, tools)
            app = server.streamable_http_app(
                stateless_http=True, json_response=True, transport_security=security
            )
            inner.append(app)
            apps[role] = app
        routes.append(Mount(f"/{name}", app=RoleGate(backend, apps)))

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for a in inner:
                await stack.enter_async_context(a.router.lifespan_context(a))
            yield
        await backend.aclose()

    return Starlette(routes=routes, lifespan=lifespan)


def asgi() -> Any:
    """Entry point for ``uvicorn dienstpilot_mcp.app:asgi --factory``."""
    import os

    return create_app(Backend(os.environ.get("API_URL", "http://localhost:8000")))
