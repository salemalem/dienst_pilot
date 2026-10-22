# ADR-009: Background solver runs, the auto-approval policy and changes to a published roster

- Status: Accepted
- Date: 2026-10-21
- Phase: 7 (C1 optimizer, C2 validator)

## Context

A solver run takes seconds to minutes, too long for an HTTP request. Once C2 exists, swaps and cover can be approved without the Planner when they break no rule (PROCESS §2), and the Planner can change a published roster. Each of these needs a clear boundary between what the system may do and what stays with the Planner.

## Decision

1. **Jobs in an arq worker.** `POST /planner/runs` stores a queued run, commits, and enqueues `run_roster`; the client polls `GET /planner/runs/{id}`. The M5 check (`POST /me/leave/check`) enqueues `check_leave` the same way. The worker (`dienstpilot.worker`, compose service `worker`) runs the same job functions the tests run inline (`dienstpilot.app.jobs`). Jobs are idempotent: a re-delivered job for a run that is no longer queued does nothing.
2. **Every variant is checked by C2 before it is stored.** A variant C2 rejects is dropped (the property test says it cannot happen). Publishing (`POST /planner/variants/{id}/publish`) checks the whole month again, records an `Approval` by the Planner and an audit event, and sets the other drafts of the month aside.
3. **Auto-approval policy** (`GET/PUT /planner/policy`, both on by default):
   - a swap is a give-away or an **exchange** (the taker gives one of their own shifts in return, `swap_offer.counter_assignment_id`); it is approved by the policy when C2, with every change applied, finds no new violation for **either** person; if the only new violation is the offerer falling below the contract-hours band, the reason is `hours_band`, otherwise `rule_violation`;
   - an accepted cover is approved by the policy when the colleague belongs to the department, C2 finds no new violation, and the shift keeps them within their contract hours (otherwise `overtime`);
   - cover by an external locum or from another department is always the Planner's decision (W7b);
   - with the policy off, everything goes to the Planner (`policy_off`). Policy approvals are logged with `{"approval": "policy"}`.
4. **Changes to a published roster** are `planning.assignment_change` records (reassign, add, remove) with a mandatory reason. The published assignments stay as approved; changes apply on top, in time order with swaps and cover. A change that introduces a violation is refused (422 with the violations). Every affected physician gets an audit event and an M11 notification (`roster_changed`). Drafts are edited directly, with live validation.
5. **Candidate lists are C2-checked.** A quick filter narrows the department down, then C2 checks the change for each colleague; every list says `check: "validated"`.

## Consequences

- The API process never runs the solver; the dev stack needs the worker service, tests need no Redis except the one arq round-trip test.
- Because swaps also check the offerer, giving a shift away while already near the lower edge of the hours band goes to the Planner. The staff app shows this before the offer (`needs_planner`); an exchange keeps both people's hours and is the usual way out (PROCESS.md Situation B).
- Swap and cover rows written before Phase 7 keep their old escalation reason `validator_unavailable`.
- Run, leave-check and change ids are random (the demo clock can stand still, and arq de-duplicates jobs by id).
- If the worker is down, a run stays `queued` and blocks a new run for that month. (Phase 9, ADR-017: the worker marks such runs `failed` when it starts, and arq's job timeout fails a run that takes too long; W3 offers a retry.)
