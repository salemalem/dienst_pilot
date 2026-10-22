"""MCP servers for DienstPilot (ARCHITECTURE §10, ADR-018).

Five small servers (``roster``, ``planning``, ``rules``, ``forecast``, ``notify``): thin typed
wrappers over the REST API. A tool call carries the signed-in user's bearer token to the API, so
roles, department scope and the privacy rules are the API's own. No tool can publish, approve,
decide or send anything: the most any tool writes is a ``Proposal`` for the Planner's inbox.
"""
