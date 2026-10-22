# ADR-008: API composition layer, demo sign-in, demo clock and engine stand-ins

- Status: Accepted; points 4 and 5 for C1 and C2 superseded by ADR-001 and ADR-009 (Phase 7); point 6 (hash chain) done by ADR-016 and point 7 superseded by ADR-017 (Phase 9)
- Date: 2026-10-21
- Phase: 3A (API for the screens)

## Context

The screens need data that spans several bounded contexts (the "Heute" screen combines the roster, the request window and cover requests). Import-linter forbids any import between contexts. The demo needs sign-in before real SSO exists, a fixed "today", and something behind each intelligence component before Phases 7 to 10 build them.

## Decision

1. **Composition layer.** `dienstpilot/app/` holds the HTTP routes and composes contexts through their public `service` modules. An import-linter contract forbids it from importing any context's `models`. Contexts stay independent of each other.
2. **Demo sign-in.** Personas from UI_SPEC §1 live in the identity context. `POST /auth/demo-login` issues an HMAC-signed bearer token (standard library only). Roles and department scope are enforced on the server in every route. OIDC replaces the login endpoint later; the roles stay.
3. **Demo clock.** A `Clock` port is the only source of time; a test fails if the backend reads the system clock. The default is the demo moment from settings. With `DEMO_MODE` on, the Administrator moves it with `PUT /demo/clock`; the value lives in Redis so it survives reloads, and the endpoint is not registered at all when `DEMO_MODE` is off.
4. **Engine ports and stand-ins.** `shared/ports.py` defines one port per component C1–C8. `dienstpilot/engines/` provides deterministic stand-ins for C3–C8 and "not implemented" adapters for C1 and C2, chosen in one registry. Every response produced by a stand-in carries an engine label; the transparency screen lists them as stand-ins. C1 and C2 endpoints answer 501.
5. **No validator, no automatic approval.** Until C2 exists, taken swaps and accepted cover go to the Planner, and candidate lists say they are unchecked. Roster edits and publishing wait for C2.
6. **Audit through a public interface.** Every write calls `audit.service.record`. The seed loader backfills events from the seeded history. The hash chain is Phase 9.
7. **Lazy cascade timers.** A cover request's 15-minute window is checked whenever cascades are read; the durable workflow engine (Phase 9) replaces this.

## Consequences

- Swapping a stand-in for a real component changes the registry, not the routes.
- Moving the demo clock forward by more than 12 hours expires tokens; sign in again.
- Some reads advance cascades (writes on GET) until Phase 9 introduces timers.
