# ADR-010: How the planner dashboard reaches the API

- Status: Accepted
- Date: 2026-10-21
- Phase: 4 (planner dashboard)

## Context

The dashboard (Next.js, App Router) runs against the real FastAPI backend with the demo sign-in. The backend has no CORS configuration, the generated `packages/api-client` held types only, and the demo tokens are bound to the demo clock.

## Decision

1. **Same-origin proxy.** `next.config.ts` rewrites `/api/:path*` to `API_URL` (default `http://localhost:8000`). The browser only talks to the dashboard's origin, so the backend needs no CORS and no token ever crosses origins. The e2e stack sets `API_URL` to its own API.
2. **Typed runtime client in `packages/api-client`.** `createApi` wraps `openapi-fetch` over the generated `paths` type, sends the bearer token, and `unwrap` turns a non-2xx answer into an `ApiError` that carries the API's rule violations (the 422 body, `packages/i18n` keys). This is the one new runtime dependency of the client package.
3. **Session = persona.** The dashboard signs in as Brandt (Planner) by default; the top bar switches to Vogel (Oversight, W12 and the read-only views) or IT-Administration (W11, demo clock). The token and persona live in `sessionStorage`, not in cookies: they are demo credentials for synthetic data, and the real OIDC sign-in replaces this layer later. A 401 (the Administrator moved the demo clock) signs in again once and screens reload their data.
4. **Screens never invent numbers.** Every figure is rendered from an API answer; where the API has none (cost, model-card links, metrics of the stand-in components) the screen shows a marked placeholder. Components C3 to C8 always show their `implementation` ("Platzhalter" / "Stand-in") exactly as the API reports it.
5. **Roles are enforced by the API; the UI only hides what a role cannot use.** The navigation per role and the "not available for this role" view are conveniences, covered by the e2e specs; the 403s of the API are the actual protection (tested in `backend/tests/api/test_permissions.py`).
6. **Publishing needs a closed request window.** A run while the window is open is a trial run (`RunOut.trial`), W3 labels it, and `POST /planner/variants/{id}/publish` answers 409. The Planner approves in W5 after closing the window in W2.

## Consequences

- One origin, no CORS surface; the dashboard build embeds `API_URL` (set it when building for another host).
- Playwright runs the whole stack in CI (Postgres, Redis, API, arq worker, dashboard) against a separate database that each run rebuilds from the seed (`apps/dashboard/e2e/reset-db.py` drops the schemas; `alembic downgrade base` cannot take rows that a run created).
- The dashboard has no client-side cache library; screens refetch on mount, after their own writes and when the session changes.
