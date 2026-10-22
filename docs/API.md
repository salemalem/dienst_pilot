# DienstPilot API

The HTTP API behind the staff app and the planner dashboard. It runs against the seeded synthetic data of the fictional Klinik für Innere Medizin, Klinikum Musterstadt (demo environment).

- **Interactive reference:** `http://localhost:8000/docs` (OpenAPI). The TypeScript client in `packages/api-client` is generated from the same schema with `make api-client`.
- **Sign-in:** `POST /auth/demo-login {"persona": "kaya"}` returns a bearer token. The personas come from UI_SPEC §1 (`GET /auth/personas`). Real single sign-on (OIDC) replaces this later.
- **Time:** every "today", deadline and countdown comes from the demo clock, Tuesday 20 October 2026, 06:00 Europe/Berlin (`GET /clock`).
  - With `DEMO_MODE` on (the dev stack), the Administrator can move the clock with `PUT /demo/clock`. The setting is stored in Redis, so it survives API reloads.
  - Tokens expire 12 hours after they are issued on the demo clock, so after moving the clock forward you sign in again.
- **Engines:** responses that use an intelligence component carry `engine: {component, implementation, version, note}`.
  - **C1 (optimizer) and C2 (validator)** are built (`implementation: "built"`, `engine/solver/`, `engine/validator/`).
  - **C3** is built: the champion of the C3 model registry, served from a committed bundle (ADR-012). **C4** is built the same way (the champion of the C4 registry; ADR-013). **C5** is built the same way (the champion of the C5 registry; ADR-014; it returns an order, never a probability). **C6** is built the same way (the champion of the C6 registry; ADR-015; an advisory hint only). **C7 and C8** are deterministic stand-ins (`implementation: "stand-in"`).
- **Background jobs:** solver runs and the M5 trade-off check run in the arq worker (compose service `worker`). The endpoint answers with an id at once; the client polls (ADR-009).
- **Rule violations** come back as i18n keys with parameters and a fix: `{rule, key: "violation.min_rest", staff_id, display_name, date, params, fix_key: "fix.min_rest", fix_params}` (`packages/i18n`). A write that would break a rule answers **422** with `{"detail": {"code": "rule_violation", "message", "violations": [...]}}`.

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

## What C2 checks, and what the Planner's policy approves (PROCESS §2, ADR-009)

| Situation | Behaviour |
|---|---|
| Candidate lists (swap audience, open offers, cover cascade, gap suggestions, W7b options) | A quick filter, then C2 checks the change for each colleague (rest periods, nights in a row, weekends, on-call limits, the free day after Bereitschaftsdienst, hours band, qualification mix). Every list says `check: "validated"` |
| A colleague takes a swap offer | Alone, or as an **exchange**: `POST /me/swap-offers/{id}/take` with `give_assignment_id` (one of the taker's own future shifts on another day); `GET /me/swap-offers` lists, per offer, `can_take_alone` and the `exchange_options` C2 accepts for both. C2 checks both people with every change applied. No new violation and the policy on: approved by the policy (`status: approved`, audit payload `{"approval": "policy"}`). Otherwise it waits for the Planner with `escalation_reason`: `hours_band` (only the offerer falls below the band), `rule_violation` or `policy_off`. The audience endpoint says beforehand whether giving the shift away needs the Planner (`needs_planner`, `own_rules`) |
| A colleague accepts a cover request | Approved by the policy when C2 finds nothing new and the shift keeps them within their contract hours; otherwise `overtime`, `rule_violation` or `policy_off`. A locum or someone from another department is always the Planner's decision (W7b) |
| The Planner decides an escalated swap or cover | The approval must still pass C2 (422 otherwise) |
| Draft edits (W4) | Direct, with live validation: the response lists the violations the change introduced and those of the changed people and days |
| Changes to a published roster (W4) | Need a `reason`; refused with 422 if they break a rule; stored as `assignment_change` records on top of the published roster; every affected physician gets an audit event and an M11 notification (`roster_changed`) |
| Publishing (W5) | The request window of the month must be closed (409 otherwise): a run while it is open is a **trial run** (`trial: true` on the run, W3 labels it). The whole month must pass C2; records the Planner's `Approval` and an audit event; the other drafts of the month become `discarded`; a published month answers 409 |
| Rest-period compliance (M10, W8, W12) | `rest_compliance` per person from C2, `rest_violations_total` per report |

Cover cascades give each colleague 15 minutes on the demo clock. The deadline is a durable timer (ADR-017): when it passes, the next colleague is asked at that instant, whether the clock ran or was moved forward with `PUT /demo/clock`, which fires every timer that has become due, in order, before it answers. Moving the clock back un-fires nothing. The same timers send in-app reminders for an open request window (7 and 2 days before it closes, only to people who have not answered) and run the nightly audit check.

The three situations of PROCESS.md §4 run against this API as scripted demo scenarios (`backend/tests/api/test_demo_scenarios.py`, synthdata ASSUMPTIONS §19).

### M5 trade-off ("Mit Tausch beantragen")

`POST /me/leave/check` returns the instant C6 hint (advisory: `coverable`, `tight` or `not_coverable`) and a `trade_off_check_id`. The hint, the version that gave it and whether the solver agreed are stored with the check; every disagreement (a hint of `coverable` against a trade-off or `not_coverable`, or `not_coverable` against `coverable`) is an audit event `leave.hint_disagreed` without a name. The screen always shows the solver's answer. Poll `GET /me/leave/checks/{id}` until `status: done`; `result.outcome` is `coverable`, `coverable_with_trade_off` (with `trade_off: {month, weekends}`), `not_coverable` (with C1's explanations) or `not_applicable` (with a `reason`). The definition and thresholds are in `synthdata/ASSUMPTIONS.md` §18; colleagues' pending requests in the month count as leave. `POST /me/leave` with `with_trade: true` needs that `check_id` for the same dates and an offered trade-off; once the Planner approves the leave, the weekends become a binding constraint when that earlier month is planned.

## Writes and the audit trail

Every write records an audit event (`GET /audit/events`) and, where it has one, publishes the domain event to the outbox in the same transaction (`dienstpilot.recording`, ADR-016). The seed loader also turns the seeded history into events: publications, leave decisions, swaps, sick reports and cover. All events are in a hash chain (one per department, one `system` chain for events without a department such as a clock change): each event has `seq`, `hash` and the chain's state is in `chain` of the response: `state` is `verified`, `stale` (last check older than 36 hours of demo time), `failed` (with `first_bad_seq` and `reason`) or `never_checked`. `POST /audit/verify` (Planner, Oversight) verifies now. A nightly timer (02:00 demo time) verifies too.

| Write | Who | Approval (PROCESS §2) |
|---|---|---|
| `PUT /me/wishes` | Physician | None: input, not a promise. Entry kinds: `unavailable` (hard), `wish_work`, `avoid_shift` (soft "rather not this shift" on that day; needs `shift_type`, never `important`) |
| `POST /me/leave` | Physician | Planner: `POST /planner/leave/{id}/decision` (a decline needs a reason) |
| `POST /me/swaps`, `POST /me/swap-offers/{id}/take` | Physician | The policy if C2-valid, else the Planner: `POST /planner/swaps/{id}/decision` |
| `POST /me/sick` | Physician | None; cover searches start for each affected shift that has not begun |
| `POST /me/cover-requests/{offer_id}` | The colleague asked | The policy if C2-valid and no overtime, else the Planner: `POST /planner/cascades/{id}/decision` |
| `POST /me/leave/check` | Physician | — (C6 hint now; queues the C1 check) |
| `POST /planner/runs` | Planner | A run changes nothing; drafts are visible to the Planner only |
| `PATCH /planner/roster/assignments` | Planner | Draft: direct. Published: reason, C2-valid, everyone affected is notified |
| `POST /planner/variants/{id}/publish` | Planner | The Planner's approval (C2-valid month) |
| `PUT /planner/policy` | Planner | — |
| `POST /planner/windows/{month}/reminders`, `/close` | Planner | — (closing cancels the automatic reminders) |
| `POST /planner/months/{month}/close` | Planner | Confirms the prepared month-end documentation: locks it and releases the payroll export |
| `POST /audit/verify` | Planner, Oversight | — (verifies the hash chain now) |
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
| M4 Wünsche / Wishes | `GET /me/wishes` (open window, entries, C4 suggestions with the numbers behind "Warum? / Why?": `evidence`, `trials`, `rate`, `department_rate`, `probability`; empty when the person switched suggestions off in M12; never available to Planner or Oversight about anybody), `PUT /me/wishes`, `POST /me/wishes/parse` (C7 preview, not saved) |
| M5 Urlaub beantragen / Request leave | `POST /me/leave/check` (C6 hint and a C1 check id), `GET /me/leave/checks/{id}` (coverable, with trade-off, not coverable), `POST /me/leave` ("Ohne Tausch" or "Mit Tausch beantragen" with `check_id`), `GET /me/leave` |
| M6 Dienst tauschen / Swap | `GET /me/swaps/audience?assignment_id=` (count only, and whether the Planner must decide), `GET /me/swap-offers` (alone or as an exchange), `POST /me/swaps`, `GET /me/swaps`, `GET /me/swap-offers`, `POST /me/swap-offers/{swap_id}/take` |
| M7 Krank melden / Report sick | `POST /me/sick` (dates only) |
| M8 Vertretungsanfrage / Cover request | `GET /me/cover-requests` (countdown, hours impact), `POST /me/cover-requests/{offer_id}` (`Übernehmen` / `Ablehnen`) |
| M9 Fairness-Bilanz | `GET /me/fairness?year=` (own counts against anonymous department statistics) |
| M10 Stunden / Hours | `GET /me/hours?month=` (contract, planned, worked, overtime, rest compliance from C2) |
| M11 Mitteilungen / Notifications | `GET /me/notifications` (roster published or changed with the reason, swaps, leave, cover requests, request-window reminders) |
| M12 Einstellungen / Settings | `GET /me/settings`, `PUT /me/settings` |

### Planner dashboard

| Screen | Endpoints |
|---|---|
| W1 Übersicht / Overview | `GET /planner/overview` (window progress, escalations, coverage of the next 14 days with the C3 band, recent changes) |
| W2 Wunschphase / Request window | `GET /planner/windows/{month}`, `POST /planner/windows/{month}/reminders`, `POST /planner/windows/{month}/close` |
| W3 Varianten / Variants | `POST /planner/runs` (202 with a run id; a run a dead worker left behind is `failed` with `error: worker_restarted` or `job_timeout`, and starting a new run is the retry), `GET /planner/runs/{run_id}` (status, `trial`, variants with metrics, the recommended one, or why no valid roster exists), `GET /planner/runs?month=` |
| W4 Dienstplan-Editor / Roster editor | `GET /roster?month=` (grid with assignment ids, absences, wish marks, coverage per shift and qualification, C2-checked gap suggestions for a published month; a draft has none). A reassignment creates a new assignment id, so an undo looks the id up again in the refreshed grid, `GET /roster?month=&variant_id=` (a draft), `PATCH /planner/roster/assignments`, `POST /planner/validate` (all violations of a month or draft) |
| W5 Freigabe / Approval | `POST /planner/variants/{variant_id}/publish` |
| W6 Anfragen / Requests inbox | `GET /planner/requests`, `POST /planner/leave/{request_id}/decision`, `POST /planner/swaps/{swap_id}/decision`, `POST /planner/proposals/{proposal_id}/decision` |
| W7 Ausfälle live / Absences live | `GET /planner/cascades` (timelines) |
| W7b Eskalation | `GET /planner/cascades/{cascade_id}` (ranked options with hours and overtime consequences), `POST /planner/cascades/{cascade_id}/decision` |
| W8 Fairness und Compliance | `GET /fairness?year=`, `GET /compliance/hours?month=`, `GET /compliance/overtime-trend` |
| W9 Copilot panel | `POST /copilot/ask` (C8 stand-in), `POST /copilot/proposals` (no publish or approve endpoint exists) |
| W10 Protokoll / Audit trail | `GET /audit/events` (filters: action, staff, since, until; `chain` says what the log may claim), `POST /audit/verify` |
| W11 Regeln und Stammdaten | `GET /master-data`, `POST /admin/rule-sets`, `GET/PUT /planner/policy` (auto-approval) |
| W12 Aufsicht / Oversight | `GET /oversight/summary?month=`, `GET /fairness`, `GET /compliance/hours`, `GET /audit/export` (with seq and hashes), month end: `GET /oversight/months`, `GET /oversight/months/{month}/report`, `GET /oversight/months/{month}/payroll?format=json\|csv` (409 until the Planner has closed the month) |
| MCP / agents (10a) | MCP servers at `/roster/mcp`, `/planning/mcp`, `/rules/mcp`, `/forecast/mcp`, `/notify/mcp` (port 8200, Streamable HTTP, same bearer token; tools listed per role); REST behind them: `GET /rules/search?q=&k=`, `GET /rules/{id}`, `POST /planner/what-if`, `GET /planner/cover-candidates?assignment_id=`, `POST /copilot/proposals` (now with `kind` and `changes`) |
| W13 KI-Transparenz | `GET /transparency/components` (C1 and C2 with the summaries in `eval/results/c1.json` and `c2.json`) |

The Staff+ department roster uses `GET /roster?month=` as well: the same grid, without absence categories, wish marks or gap suggestions.

### Dashboard access

The dashboard calls the API through its own origin: Next.js proxies `/api/*` to the backend (`API_URL`, default `http://localhost:8000`), so no CORS is needed (ADR-010). The browser signs in with `POST /auth/demo-login` as Brandt by default; the persona switch (Vogel, IT-Administration) signs in again.

### Staff app access

The staff app (Expo) calls the API at `EXPO_PUBLIC_API_URL` (default `http://localhost:8000`). Expo web needs CORS: with `DEMO_MODE` on, the API answers preflights for the origins in `CORS_ORIGINS` (default `http://localhost:8081,http://localhost:8083`), and for no other origin; with `DEMO_MODE` off it sends no CORS headers. Native apps are not subject to CORS (ADR-011).
