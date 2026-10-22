# ADR-017: Durable workflows and timers due in demo time

- Status: Accepted; replaces ADR-008 point 7 (lazy cascade timers) and the "stuck run" note of ADR-009
- Date: 2026-10-22
- Phase: 9 (events, audit trail, durable workflows)

## Context

Cover requests had a 15-minute deadline that was checked whenever a cascade was read (`operations.advance`). That worked for a demo but writes on a GET, depends on somebody reading, and loses the idea of "what happens next" when the process dies. ARCHITECTURE §9.1 asks for durable state machines with timers, and the demo needs to move the clock forward and see everything that became due happen, in order.

## Decision

1. **State is in Postgres only.** `workflow.instance` (kind, business key, state, data) holds the position of a workflow; `workflow.timer` holds what is due when. The transitions of the four workflows (sick-call cascade, swap approval, request-window reminders, month end) are data in `shared/workflows/machines.py`; a move the machine does not allow raises. The existing tables (`cover_cascade`, `swap_offer`, …) stay the source of truth for their business state; the instance records the workflow position and owns the timer.
2. **Timers are due in demo time.** `due_at` is an instant of the demo clock. `fire_due` runs every timer with `due_at <= now`, one at a time, in `(due_at, id)` order. A handler stamps its effects with the timer's `due_at`, not with "now": after a jump of two hours, the second colleague of a cascade is asked at the moment the first deadline expired, exactly as if the clock had run. Timers armed while firing that are already due fire in the same loop, so a cascade runs to its end in one call.
3. **Moving the clock fires timers before the call returns.** `PUT /demo/clock` sets the clock and calls `fire_due`. Moving it back un-fires nothing (`make seed` resets the demo). The worker also ticks every second, and the API calls `fire_due` first thing in the handlers that read or write what timers change, so the system is correct with the worker stopped.
4. **Exactly once.** `fire_due` takes a transaction-level advisory lock when something is due, so a read and the worker (or two reads) serialise instead of racing; the one that waits finds the timers done. Each timer row is locked and marked fired in the same transaction as its handler's changes. Defence in depth for the cascade: the cover offer and its cascade are row-locked by both the timeout and the colleague's answer, whoever is second sees an offer that is no longer pending, and an answer cancels the offer's timer. Tests: eight concurrent callers (API reads and worker calls) after a deadline, then after a four-hour jump, and nobody is asked twice; removing the locks makes that test fail.
5. **A worker that dies loses nothing.** The handler runs in the same transaction as the "fired" mark; if the process dies, the transaction rolls back and the timer is still due for the next worker (tested by killing a firing after the work was done and before the commit). A handler that raises is retried up to three times, then set aside (`failed_at`), so one bad timer cannot block the others.
6. **Redis is only a wake-up.** Deferred arq jobs would lose their timers when Redis is flushed. Instead an arq cron ticks every second and asks Postgres what is due.
7. **Recurring timers re-arm themselves.** The nightly chain check (02:00) arms the next night when it fires. A jump over many days collapses the skipped nights into one more check rather than running one per night.
8. **Reminders.** For an open request window, in-app reminders are armed 7 and 2 days before it closes, only for reminders still in the future when the window is seeded or opened, and go only to recipients who have not answered. Closing the window cancels them. The manual reminder in W2 stays.
9. **Month end.** When a month is over (00:00 on the first of the next month, demo time) the `month.prepare` timer computes the documentation from the same functions the screens use and stores it (`fairness.month_report`). The Planner confirms it with one click (`POST /planner/months/{month}/close`), which locks it (the stored report is never replaced; roster changes already only reach future days) and releases the payroll export. `MonthClosed` is consumed to prepare the next month. Narrative text is a labelled placeholder until Phase 10.
10. **Runs left behind by a dead worker.** arq's job timeout cancels a run that takes too long; the job marks its run `failed` (`job_timeout`). At worker start, runs left in `running`, and `queued` runs whose job is no longer on the queue, are marked `failed` (`worker_restarted`). W3 shows the failure and offers a retry.

## Consequences

- API handlers no longer write on read for deadlines in a way a reader could notice, but they still call `fire_due`; a request can therefore wait for a firing in progress.
- Cascades opened before this phase get their workflow instance lazily on their next transition.
- The advisory lock serialises firing for the whole database; one department makes that irrelevant, many would want a lock per department.
