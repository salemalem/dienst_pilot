"""Reaching the MCP servers over Streamable HTTP with the signed-in user's own token."""

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from dienstpilot_agents.copilot.tools import Connect


def mcp_connect(base_url: str, token: str) -> Connect:
    """Return a ``connect(server)`` that opens a client for ``<base_url>/<server>/mcp``."""

    def connect(server: str) -> Client:
        http = httpx2.AsyncClient(
            base_url=base_url, headers={"authorization": f"Bearer {token}"}, timeout=60.0
        )
        return Client(streamable_http_client(f"{base_url}/{server}/mcp", http_client=http))

    return connect
