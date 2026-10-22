# ADR-018: MCP servers as REST wrappers, a usage log instead of Langfuse, and the key in .env

- Status: Accepted
- Date: 2026-10-23
- Phase: 10a (MCP servers and RAG)

## Context

C8 reaches data only through MCP tools (ARCHITECTURE §10). The tools must have exactly the power of the signed-in user and no power to publish or approve (CLAUDE.md, architecture rule 3). The architecture also named Langfuse (self-hosted) for LLM traces and token cost, and the Anthropic key has to enter the system somehow.

## Decision

1. **Thin wrappers over the REST API, with token pass-through.** `mcp_servers/` (package `dienstpilot_mcp`) holds five servers (`roster`, `planning`, `rules`, `forecast`, `notify`), each tool one typed wrapper over one REST endpoint. A request must carry the demo bearer token; the server asks the API itself (`GET /me`) whether it is valid and what role it has, then forwards the token on every call. Roles, department scope, absence-category rules and every other privacy rule are therefore the API's, and cannot drift from a second implementation. An import-linter contract forbids the package to import the backend or the agents. Real OAuth (audience-bound tokens instead of pass-through) is not built; the demo login is the only sign-in, and the status says so.
2. **Role-scoped tool lists.** Each server is built once per role and the role picks the instance: the Planner sees every tool; Oversight only read tools (`run_what_if` is a calculation that writes nothing, and counts as a read); staff roles get 403. The API still refuses what a role may not do.
3. **No power beyond a proposal.** The only tools that write are `create_proposal` and `draft_announcement`, both of which create a `Proposal` row (kind `change` or `announcement`) in the Planner's inbox. Nothing applies, publishes, approves or sends. A test lists every tool for every role and fails on a name containing publish, approve, send, decide, apply, accept, close, delete or release, on a missing annotation, and on a missing output schema. Acting on a proposal is a separate, validated change by the Planner.
4. **Annotations and schemas.** Every tool declares `readOnlyHint`, `destructiveHint` (always false), `idempotentHint` and `openWorldHint`, and a typed output schema from Pydantic models that list what a tool returns and leave the rest out: staff are ids, never names; the absence category and free text never appear.
5. **One process, five mounts.** The compose service `mcp` mounts the five servers at `/<server>/mcp` (Streamable HTTP, stateless, JSON responses). Mounting a subset makes one of them a separate deployment (`create_app(only=...)`).
6. **A usage log instead of Langfuse** (amended by ADR-020: the log is a committed ledger file, not a Postgres table, so that `make seed` cannot erase the budget). Self-hosted Langfuse needs Postgres, ClickHouse, Redis and S3-compatible storage; that does not fit the one-VPS design. LLM calls (from 10b) are logged to a Postgres table (component, model, prompt version, input, output and cache tokens, latency, outcome; never prompt or response text) read by `eval/cost_model.py`, and traced with OpenTelemetry. Every doc that named Langfuse (CLAUDE.md, ARCHITECTURE §14, PLAYBOOK.md) now says so. Langfuse may be added later; nothing claims it.
7. **The key.** `ANTHROPIC_API_KEY` is read by `Settings` from the environment or from the git-ignored `.env` (the repository's and the working directory's), as a `SecretStr`; the compose services take `.env` as an optional env file. Tests check that `.env` is git-ignored, that no key-shaped string is committed and that the key does not appear in a settings dump. Model IDs stay configuration (`LLM_MODEL_INTAKE`, `LLM_MODEL_COPILOT`).

## Consequences

- Every tool call is one HTTP round trip to the API, and `GET /me` adds another; fine for an agent that makes a handful of calls.
- Token pass-through is acceptable for a demo login, not for a deployment with real single sign-on: that needs audience-bound tokens and is not built.
- New endpoints made for the tools (`/rules/search`, `/planner/what-if`, `/planner/cover-candidates`) are normal API endpoints with the usual privacy tests.
