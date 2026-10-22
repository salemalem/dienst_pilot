# ADR-013: C4 serving, the person-only privacy boundary, and the same promotion convention

- Status: Accepted
- Date: 2026-10-22
- Phase: 8b (C4 preference learner)
- Builds on: ADR-012

## Context

C4 infers likely preferences from a person's own wishes and swap offers. Unlike C3 it is individual-level, which makes the privacy boundary part of the design: the Planner and Oversight must never see what the model infers, only what a person has confirmed (works-council review, ARCHITECTURE §15).

## Decision

1. **Same convention as C3.** `ml/preference_learner/PROMOTION_RULE.md` is committed before any model is fitted; its hash is recorded in `eval/results/c4.json` and a test fails if it changes afterwards. The best baseline (pooled department rates or raw per-person rates) is chosen on 2022 to 2024 cross-validation; the hierarchical Beta-Binomial learner is judged once on the held-out 2025. If it fails, the baseline stays champion and every surface says so. The first run did not pass the rule, so the raw baseline is served.
2. **The bundle is department-level only.** `bundle.json` holds 28 pooled rates per process and two concentrations. No person-level value and no staff identifier is written to it; tests inspect the committed file for any key outside the allowed set, any UUID-like value, and any staff id of the dataset. A person's own counts arrive with each request and are combined with the bundle at request time.
3. **Computed per request, for the person only, never stored.** `GET /me/wishes` is the only endpoint that returns suggestions; the adapter keeps no state between calls. When a person switches suggestions off (M12), the learner is not called and their history is not even loaded; a test counts calls. A privacy test walks every GET endpoint for every persona and fails if an inferred-preference key appears anywhere except `/me/wishes`; Oversight and Admin get 403 there.
4. **The port takes the person's own history as context.** `PreferenceLearner.suggest(wishes, swapped_away, context)` with `PreferenceContext(answered_months, unavailable_days, assigned)`, filled by the application layer from the person's own rows, so the engine needs no database access and no cross-context import. `PreferenceSuggestion` carries the numbers behind "Warum? / Why?": events, trials, the person's rate, the department rate and a probability.
5. **A swap offer counts as dislike whether or not it was accepted.** Using accepted swaps only would discard evidence the person gave.
6. **No new dependencies.** numpy for serving; SciPy (already in the `train` extra, ADR-012) only for the marginal likelihood in training. An import-linter contract extends to forbid `scipy` in the API and in serving-side C4 code.
7. **Truth recovery lives in `eval/` only** (`eval/src/dienstpilot_eval/c4_truth.py`, ASSUMPTIONS §14) and plays no part in promotion.
8. **A confirmed "avoid" chip is a soft preference for that weekday × shift type, never a block.** The wish model had only "kann nicht" (a hard block for the whole day) and "möchte arbeiten", so it could not say "rather not this shift". The smallest addition: a third request-window entry kind `avoid_shift` (one day, one named shift, never important), added by an expand-only migration that widens the `kind` CHECK constraint (revision 0005), accepted by `PUT /me/wishes`, and passed to the solver as `Problem.avoid` (`AvoidIn`). The solver adds a penalty of one unmet wish (`profile.wishes`) whenever that shift is assigned to that person. It adds no constraint and touches no hard input: the person stays available for every other shift, `blocked`, `leave` and the wishes are unchanged, and C2 treats the entry as nothing at all. Tests pin it (a backend test compares the solver problem before and after confirming, a solver test checks the roster stays valid and moves the shift). "Avoid" entries are not counted in the wishes-granted metrics, so the benchmark is unchanged.

## Consequences

- The result file belongs to a data identity, the C4 source hash, the rule hash and the served bundle hash; `eval/tests/test_c4_results_are_current.py` fails if any drifts. The C3 source hash excludes C4 files, so adding C4 did not invalidate `c3.json`.
- If the pooled baseline ever wins the rule, the staff app shows no chips (it has no personal signal) and says which model is served.
- M4 earlier turned a confirmed "avoid" chip into a hard "kann nicht" for every such weekday; that was wrong (the model infers a dislike of one shift, not unavailability) and is fixed by decision 8. The chip no longer reappears once an equivalent entry exists.
