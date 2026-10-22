# ADR-016: Event outbox, Redis Streams, idempotent consumers and the audit hash chain

- Status: Accepted
- Date: 2026-10-22
- Phase: 9 (events, audit trail, durable workflows)

## Context

ARCHITECTURE §8 promised three things that did not exist yet: domain events written in the same transaction as the state change and relayed to Redis Streams, consumers that handle each event once, and an audit trail whose entries cannot be changed or removed without anyone noticing. Audit event ids have been random since Phase 4 (the demo clock can stand still, so two events can share an instant), so neither the id nor the timestamp can order the log.

## Decision

### Events

1. **Outbox.** `events.outbox` (shared kernel) takes one row per event inside the caller's transaction, validated against its schema first. A rolled-back change takes its events with it. Every write path goes through `dienstpilot.recording.record`, which appends the audit event and publishes the domain event it stands for, so the log and the stream cannot disagree. Events that have no audit action (a run finishing, a cover list running out, both from background code) are published directly.
2. **Relay.** A one-second tick on the arq worker sends unrelayed rows, oldest first, to the stream `dienstpilot:events` (`SELECT … FOR UPDATE SKIP LOCKED`, then `XADD`, then mark). A crash between `XADD` and the commit sends a row twice. That is accepted: delivery is at least once, and consumers deduplicate.
3. **Consumers.** One Redis consumer group per consumer. For each entry, in one database transaction, the consumer inserts `(consumer, event_id)` into `events.processed`; only if that row is new does the handler run; then the transaction commits and the entry is acknowledged. A crash before the acknowledgement redelivers the entry and the insert finds the row. A handler that raises rolls back and leaves the entry pending. Redis is never the source of truth: the outbox is, so a flushed Redis loses nothing that was not yet relayed.
4. **Schemas.** JSON Schema files `shared/events/schemas/<EventType>.v<N>.json`. Payloads carry ids only, never names and never an absence category, and `additionalProperties` is false. `MANIFEST.json` pins the SHA-256 of every file; a contract test fails if a published file was edited, so a breaking change must be a new version. Both versions can be loaded and consumed during a migration.
5. **What consumes what today.** One consumer is built, `month_end`, which reacts to `MonthClosed` by preparing the following month. All other events are published and have no consumer yet; the Assistant context (Phase 10) will be the next. This is stated in the status table instead of implying more.

### Audit hash chain

1. `hash = sha256(prev_hash ‖ canonical_json(event))`, with `‖` as concatenation of the 64 hex characters of the previous hash and the UTF-8 bytes of the canonical JSON. Canonical JSON (format version 1): sorted keys, no whitespace, UTC timestamps with microseconds, lower-case UUIDs; the field list is in `audit/chain.py`. The first entry of a chain has the previous hash `0 × 64`.
2. **One chain per department, plus a `system` chain** for events that belong to no department (a change of the demo clock). Appending locks the chain's head row, assigns `seq` (1, 2, 3 …, no gaps) and computes the hash. Two writers of the same department queue up; different departments do not wait for each other.
3. **Order is `seq`**, never the id or the timestamp. W10 lists newest first by `seq`.
4. **History is chained too.** The seed loader orders the derived history by a total order that does not depend on how it was assembled, chains it, and runs the verifier once. Migration 0007 does the same for an existing database (order: `occurred_at`, then `id`) with a frozen copy of the canonical JSON; a test checks that the copy and the application code agree. Migration 0008 then makes the four columns required. Both are in the same release, which is safe because every write path sets them before 0008 runs, and 0008 refuses to run if a row is left unchained. A test upgrades a pre-Phase-9 database that holds seeded and app-written events.
5. **Verifier.** `verify_chain` recomputes a whole chain and compares it with the stored head, so a changed row, a removed row, a reordered row and a removed tail are all found (tests for each). It runs nightly at 02:00 demo time as a timer (ADR-017) and on demand (`POST /audit/verify`). Results are stored in `audit.chain_check`.
6. **What W10 may claim.** "Protokoll vollständig und unverändert" appears only when the last full check passed, is not older than 36 hours of demo time, and every entry appended since links to the verified head (a cheap check made on each read). A change to an older entry is found by the next full check, not by the read. A failed check shows where it failed; a check that is too old says so; a log never checked says so.

## Consequences

- Every write holds the department's chain head until commit. At this scale (one department) that is fine; it would have to change before many departments write concurrently in long transactions.
- Hashes prove consistency of the stored chain, not who wrote it: an attacker with database write access who recomputes the whole chain is not detected by the chain alone. Exporting the head hash (it is in the month-end report and in the export) lets an outside party pin it.
- Events from before Phase 9 have no domain events in the outbox; the stream starts at Phase 9.
