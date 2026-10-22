"""The REST API as the servers see it: the caller's bearer token, JSON in and out."""

import contextlib
from contextvars import ContextVar
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

_token: ContextVar[str | None] = ContextVar("dienstpilot_mcp_token", default=None)
_role: ContextVar[str | None] = ContextVar("dienstpilot_mcp_role", default=None)


def current_token() -> str:
    """Return the bearer token of the request being served."""
    token = _token.get()
    if token is None:
        raise ToolError("not signed in")
    return token


def current_role() -> str | None:
    """Return the role of the request being served."""
    return _role.get()


class Backend:
    """Calls the REST API with the caller's own token (token pass-through, ADR-018)."""

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Remember the API address; ``transport`` lets tests call an in-process app."""
        self._client = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=30.0)

    async def whoami(self, token: str) -> dict[str, Any] | None:
        """Return ``GET /me`` for the token, or None if the API does not accept it."""
        r = await self._client.get("/me", headers={"authorization": f"Bearer {token}"})
        return r.json() if r.status_code == 200 else None

    async def request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None
    ) -> Any:
        """Call the API as the current user. Errors become tool errors the model can read."""
        r = await self._client.request(
            method,
            path,
            params=params,
            json=json,
            headers={"authorization": f"Bearer {current_token()}"},
        )
        if r.status_code >= 400:
            detail: Any = ""
            with contextlib.suppress(ValueError):
                detail = r.json().get("detail", "")
            if isinstance(detail, dict):
                detail = detail.get("message", "")
            raise ToolError(f"API answered {r.status_code}: {detail}".strip())
        return r.json()

    async def get(self, path: str, **params: Any) -> Any:
        """GET with query parameters."""
        return await self.request(
            "GET", path, params={k: v for k, v in params.items() if v is not None}
        )

    async def post(self, path: str, body: Any) -> Any:
        """POST a JSON body."""
        return await self.request("POST", path, json=body)

    async def aclose(self) -> None:
        """Close the connection pool."""
        await self._client.aclose()


def bind(token: str, role: str) -> tuple[Any, Any]:
    """Set the token and role of the request; returns the reset handles."""
    return _token.set(token), _role.set(role)


def unbind(handles: tuple[Any, Any]) -> None:
    """Undo ``bind``."""
    _token.reset(handles[0])
    _role.reset(handles[1])
