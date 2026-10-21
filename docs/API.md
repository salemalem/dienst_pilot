# DienstPilot API

The HTTP API behind the staff app and the planner dashboard. It runs against the seeded synthetic data of the fictional Klinik für Innere Medizin, Klinikum Musterstadt (demo environment).

- **Interactive reference:** `http://localhost:8000/docs` (OpenAPI). The TypeScript client in `packages/api-client` is generated from the same schema with `make api-client`.
- **Sign-in:** `POST /auth/demo-login {"persona": "kaya"}` returns a bearer token. The personas come from UI_SPEC §1 (`GET /auth/personas`). Real single sign-on (OIDC) replaces this later.
- **Time:** every "today", deadline and countdown comes from the demo clock, Tuesday 20 October 2026, 06:00 Europe/Berlin (`GET /clock`).
  - With `DEMO_MODE` on (the dev stack), the Administrator can move the clock with `PUT /demo/clock`. The setting is stored in Redis, so it survives API reloads.
  - Tokens expire 12 hours after they are issued on the demo clock, so after moving the clock forward you sign in again.
- **Engines:** responses that use an intelligence component carry `engine: {component, implementation, version, note}`.
  - **C3–C8** are deterministic stand-ins (`implementation: "stand-in"`).
  - **C1 (variant generation) and C2 (validation)** are not implemented yet. Their endpoints answer **501** with `{"detail": {"code": "engine_not_implemented", "component", "planned_phase": 7, "message"}}`.

## Roles and department scope (PROCESS §1, §2)

| Role | Personas | May |
|---|---|---|
| Staff | Dr. Kaya, Dr. Mehta, Dr. Weber, Dr. Alvarez, Dr. Nowak | Own roster, hours, fairness, requests; colleagues on the same shift |
| Staff+ | Dr. Lorenz, Dr. Schulz | Everything Staff may, plus the department roster and the qualification coverage per shift |
| Planner | Dr. Brandt, Prof. Hoffmann | Everything in the department; decides leave, escalated swaps and cover, proposals |
| Oversight | Katrin Vogel | Read only: hours, overtime and rest compliance per person; fairness as anonymous statistics; audit trail |
| Administrator | IT-Administration (Demo) | Rules and master data; the demo clock. No daily operation |

Every query is limited to the signed-in user's department.

## Privacy in the API

- **Absences:** only the Planner sees an absence's category. Everyone else gets `{"status": "absent"}` (the UI shows "abwesend" / "absent"). This includes the audit trail.
- **Hours and fairness detail:** a person's own come back only to themselves and to the Planner. Oversight gets hours per person (payroll, working-time records) but fairness only as statistics without names. Staff see department fairness only as anonymous statistics.
- **Nothing to leak:** there is no diagnosis field and no field for a requester's leave reason anywhere. Only the Planner's reason for a decline is stored, and it is shown to the requester.
- **Tested:** a test walks every GET endpoint as every persona and fails if any of this is violated.

## Until the validator (C2) exists (Phase 7)

| Situation | Behaviour now |
|---|---|
| A colleague takes a swap offer | Waits for the Planner (`status: pending_approval`, `escalation_reason: validator_unavailable`) instead of being approved automatically |
| A colleague accepts a cover request | Same: the Planner confirms it |
| Candidate lists (swap audience, cover cascade, gap suggestions, W7b options) | A basic filter: on the roster that day, the right role and qualifications, no other working shift, not on leave or absent. Rest periods and monthly limits are **not** checked; every list says `check: "unchecked"` |
| Roster edits (W4), live validation (W4), approve and publish (W5) | 501 |
| Variant generation (W3), "Mit Tausch beantragen" (M5) | 501 (C1) |
| Rest-period compliance (M10, W8, W12) | `null`, with `available_from_phase: 7` |

Cover cascades give each colleague 15 minutes on the demo clock. When a request times out, the next colleague is asked the next time the cascade is read. Durable timers come with the workflows in Phase 9.

## Writes and the audit trail

Every write records an audit event (`GET /audit/events`). The seed loader also turns the seeded history into events: publications, leave decisions, swaps, sick reports and cover. The hash chain comes in Phase 9 (`chain_verified: null`).

| Write | Who | Approval (PROCESS §2) |
|---|---|---|
| `PUT /me/wishes` | Physician | None: input, not a promise |
| `POST /me/leave` | Physician | Planner: `POST /planner/leave/{id}/decision` (a decline needs a reason) |
| `POST /me/swaps`, `POST /me/swap-offers/{id}/take` | Physician | Planner while C2 is missing: `POST /planner/swaps/{id}/decision` |
| `POST /me/sick` | Physician | None; cover searches start for each affected shift that has not begun |
| `POST /me/cover-requests/{offer_id}` | The colleague asked | Planner while C2 is missing: `POST /planner/cascades/{id}/decision` |
| `POST /planner/windows/{month}/reminders`, `/close` | Planner | — |
| `POST /copilot/proposals` | Planner | A proposal changes nothing; the Planner accepts or dismisses it |
| `POST /admin/rule-sets` | Administrator | A new version starts in the future; old rosters keep theirs |
| `PUT /me/settings` | Everyone except Oversight | — |
| `PUT /demo/clock` | Administrator, DEMO_MODE only | — |

## Screens → endpoints

### Staff app

| Screen | Endpoints |
|---|---|
| M1 Anmeldung / Sign in | `GET /auth/personas`, `POST /auth/demo-login`, `GET /me` |
| M2 Heute / Today | `GET /me/today` (next shift with colleagues, open window, open cover requests) |
| M3 Mein Dienstplan / My roster | `GET /me/roster?month=YYYY-MM` (shifts, wish marks granted/missed, published by and when), `GET /me/fairness` (the one-line balance), `GET /me/settings` (calendar sync) |
| M4 Wünsche / Wishes | `GET /me/wishes` (open window, entries, C4 suggestions), `PUT /me/wishes`, `POST /me/wishes/parse` (C7 preview, not saved) |
| M5 Urlaub beantragen / Request leave | `POST /me/leave/check` (C6 hint; trade-off waits for C1), `POST /me/leave` ("Ohne Tausch beantragen"; `with_trade: true` → 501), `GET /me/leave` |
| M6 Dienst tauschen / Swap | `GET /me/swaps/audience?assignment_id=` (count only), `POST /me/swaps`, `GET /me/swaps`, `GET /me/swap-offers`, `POST /me/swap-offers/{swap_id}/take` |
| M7 Krank melden / Report sick | `POST /me/sick` (dates only) |
| M8 Vertretungsanfrage / Cover request | `GET /me/cover-requests` (countdown, hours impact), `POST /me/cover-requests/{offer_id}` (`Übernehmen` / `Ablehnen`) |
| M9 Fairness-Bilanz | `GET /me/fairness?year=` (own counts against anonymous department statistics) |
| M10 Stunden / Hours | `GET /me/hours?month=` (contract, planned, worked, overtime; rest compliance after C2) |
| M11 Mitteilungen / Notifications | `GET /me/notifications` |
| M12 Einstellungen / Settings | `GET /me/settings`, `PUT /me/settings` |

### Planner dashboard

| Screen | Endpoints |
|---|---|
| W1 Übersicht / Overview | `GET /planner/overview` (window progress, escalations, coverage of the next 14 days with the C3 band, recent changes) |
| W2 Wunschphase / Request window | `GET /planner/windows/{month}`, `POST /planner/windows/{month}/reminders`, `POST /planner/windows/{month}/close` |
| W3 Varianten / Variants | `GET /planner/runs?month=`, `POST /planner/runs` → 501 (C1) |
| W4 Dienstplan-Editor / Roster editor | `GET /roster?month=` (grid, absences, wish marks, coverage per shift and qualification, gap suggestions), `PATCH /planner/roster/assignments` → 501 (C2), `POST /planner/validate` → 501 (C2) |
| W5 Freigabe / Approval | `POST /planner/variants/{variant_id}/publish` → 501 (C2) |
| W6 Anfragen / Requests inbox | `GET /planner/requests`, `POST /planner/leave/{request_id}/decision`, `POST /planner/swaps/{swap_id}/decision`, `POST /planner/proposals/{proposal_id}/decision` |
| W7 Ausfälle live / Absences live | `GET /planner/cascades` (timelines) |
| W7b Eskalation | `GET /planner/cascades/{cascade_id}` (ranked options with hours and overtime consequences), `POST /planner/cascades/{cascade_id}/decision` |
| W8 Fairness und Compliance | `GET /fairness?year=`, `GET /compliance/hours?month=`, `GET /compliance/overtime-trend` |
| W9 Copilot panel | `POST /copilot/ask` (C8 stand-in), `POST /copilot/proposals` (no publish or approve endpoint exists) |
| W10 Protokoll / Audit trail | `GET /audit/events` (filters: action, staff, since, until) |
| W11 Regeln und Stammdaten | `GET /master-data`, `POST /admin/rule-sets` |
| W12 Aufsicht / Oversight | `GET /oversight/summary?month=`, `GET /fairness`, `GET /compliance/hours`, `GET /audit/export` |
| W13 KI-Transparenz | `GET /transparency/components` |

The Staff+ department roster uses `GET /roster?month=` as well: the same grid, without absence categories, wish marks or gap suggestions.
