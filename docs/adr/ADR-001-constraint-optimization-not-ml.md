# ADR-001: The roster is built by constraint optimization, not by a learned model

- Status: Accepted
- Date: 2026-10-21
- Phase: 7 (C1 optimizer, C2 validator)

## Context

A duty roster must keep every hard rule: coverage per shift and qualification, rest periods, night runs, weekend and on-call limits, the free day after Bereitschaftsdienst, the contract-hours band and approved leave. One broken rule makes a roster unusable, and the Planner has to be able to see why a roster looks the way it does. Wishes, fairness and overtime are trade-offs the Planner weighs. The synthetic history has five years of manually planned rosters that themselves break rules after in-month changes.

A learned model (for example one trained to imitate the historical rosters) would learn the manual planner's habits including their rule breaks, could not guarantee any rule, and could not explain an infeasible month.

## Decision

1. **C1 is a CP-SAT model** (Google OR-Tools). Hard rules are constraints; wishes, burden spread, overtime, isolated nights and stability are a weighted objective. Rules come from the versioned rule set (data), not from code.
2. **Two to three variants per run** from different weight profiles (wishes first, zero overtime, balanced) plus a diversity constraint, so the Planner chooses between real trade-offs. The recommended profile's weights are tuned on months before the held-out year (`eval/tune_profiles.py`).
3. **Infeasibility is explained.** Constraint groups are guarded by assumption literals; the sufficient assumptions for infeasibility become i18n sentences (`infeasible.*`).
4. **C2 is a second, independent implementation** of the same rules (N-version). It checks every solver output before it is stored and every change before it is written. It is cross-checked against the generator's independent checker on every published month and on random changes (`eval/run_validator_eval.py`).
5. **Reproducible runs.** The solver stops at a deterministic time limit with interleaved multi-thread search and a fixed seed, and the model is built in a fixed order; the wall-clock limit is only a guard. Each run stores the solver version, validator version and full configuration.
6. **ML stays where uncertainty is.** Absence forecasts, preference learning, cover acceptance and the leave surrogate (C3–C6) estimate inputs; they never place an assignment.

## Consequences

- Every roster the system proposes passes C2; a property test in CI checks this on perturbed real months.
- Results depend on the deterministic time budget, not on machine speed; reported solve times (wall clock) are not reproducible and are kept apart from the results hash.
- When the rules change, only the rule set changes; both C1 and C2 read it.
- The benchmark compares each month independently from the same as-worked history; C1's months are not chained into a year (stated as a limitation in `eval/results/benchmark.json`).
