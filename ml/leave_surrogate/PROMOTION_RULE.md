# C6 promotion rule and label protocol (written before any label was generated or model fitted)

This file was committed before any C6 label was generated, before any model was fitted and before
2025 was scored. Its sha256 is recorded in `eval/results/c6.json`; a test fails if the file changes
without the result being regenerated.

## What is modelled

One row per **simulated leave request** in one calendar month. The label is the answer of the
product's own M5 check (C1 and C2, `check_leave` in `backend/.../app/jobs.py`, synthdata
ASSUMPTIONS §18), computed by the same function the product runs, one of
`coverable`, `coverable_with_trade_off`, `not_coverable`. The surrogate only drives the instant
hint; the solver's answer is the one shown. Requests that span two months, or whose month is
already published, get no label (the product answers `not_applicable`).

## Request simulation (fixed)

- **Months.** Train: every month of 2021-01 to 2024-12. Test: every month of 2025. About 62
  requests per training month (3,000 in total) and about 83 per test month (1,000 in total).
  If the pilot projects more than 4 hours of label generation the totals may be cut to 2,000 and
  700, after the user has been told; nothing else may change.
- **Request.** Block of 5, 10 or 15 working days (probabilities 0.4, 0.4, 0.2) starting on a
  Monday and ending inside the same month; the start Monday is uniform over the month's
  Mondays that leave room. Requester: uniform over people with a contract on every day of the
  window and no own leave in it. Submission time: 60 to 150 days before the start, uniform.
- **State at submission.** Every leave request of the dataset submitted before that moment,
  except those already declined by then, counts as leave (approved and still-pending alike, the
  product's cautious reading). No wishes and no unavailability (none exist 60 days out). The
  year-to-date burden ledger is taken as of the start of the month (a simplification).
- **Two strata, 50 % each (fixed):**
  - *natural*: the state as it was;
  - *stress*: k extra colleagues, k uniform from 1 to 10, are put on leave over the whole
    window (a counterfactual pile-up; the real planner stops approving at 6 concurrent, so real
    states almost never reach the boundary). Colleagues are drawn uniformly among people with a
    contract on every day of the window, not the requester.
- Seeds: `20261020` for the whole sample; a request's draws depend only on its index, so the
  sample is reproducible and cached by request hash, solver version, validator version and
  dataset manifest hash.
- **Fidelity.** Labels are solved with the product's `CHECK_CONFIG` except `workers=2` (so five
  processes can run in parallel). 200 labels, drawn at random, are re-solved with the exact
  `CHECK_CONFIG` (`workers=8`); the share that differs is reported.

## Target (fixed before the pilot)

Labels always keep all three classes. If, in the training labels, `coverable_with_trade_off` is
under 5 % of rows or under 100 rows, the target is **binary**: y = 1 only if the solver says
`coverable`, y = 0 for `coverable_with_trade_off` and `not_coverable`. A false yes is then a hint
of "coverable" where the solver says trade-off or no. Otherwise the target has three classes and
"precision of coverable" is the precision of the class `coverable`.

## Features (fixed; `ml/src/dienstpilot_ml/features/leave.py`, shared by training and serving)

Computed from the state at submission for the request window: minimum and mean daily coverage
slack (people available minus required headcount minus people on leave), qualification slack
(minimum over days, per qualification the demand names), overlapping leave (maximum and mean per
day: approved, pending), number of distinct overlapping colleagues, public holidays and
school-holiday days in the window, weekend days, length in days, notice in days, requester's
role, flags for the requester's qualifications, month of the year.

**Excluded:** any person identifier, age, gender, nationality, family status, personal leave
history, reasons, sickness. The bundle holds trees, thresholds and the feature list only. The
ground truth (`_truth/`) is not read: labels come from the solver.

## Models

- **B1, stand-in rule:** "yes" iff the largest number of colleagues on leave on a day of the window
  is at most limit - 2 (limit 6), exactly the hint outcome `coverable` of the stand-in. Hints
  `tight` and `not_coverable` count as no.
- **B2, logistic regression:** the same features, categorical ones one-hot, numeric ones
  standardised with training means and deviations, L2 penalty with inverse strength `C` = 1,
  L-BFGS from zeros (numpy and scipy, as in C5).
- **Learner, LightGBM classifier.** `learning_rate` 0.05, `deterministic=True`,
  `force_row_wise=True`, one thread, `seed=20261020`. Grid, chosen by rolling-origin log-loss (mean
  over the folds below): `num_leaves` in {4, 8}, `min_child_samples` in {20, 40}, `n_estimators` in
  {100, 200}. Served: fitted on all of 2021 to 2024 with the chosen grid point.

## Data and splits

- Training, model selection and the operating point use 2021 to 2024 labels only.
- Rolling-origin cross-validation by calendar year: test years 2022, 2023, 2024, each trained on
  all earlier years. No random splits.
- 2025 is the final held-out test, scored once after the models, the grid, the thresholds and this
  rule are frozen.

## Operating point (fixed)

A precision comparison between classifiers is meaningless unless recall is pinned (any classifier
raises precision by saying yes less often). For B2 and the learner the threshold on P(coverable)
is the one that **maximises precision subject to out-of-fold recall at least B1's out-of-fold
recall**, chosen on the out-of-fold predictions of 2022 to 2024 and then frozen. Ties go to the
lower threshold. The hint is `coverable` for P at or above this threshold. Hint `not_coverable`
for P under 0.10 (fixed, reported, not part of promotion); in between the hint is `tight`.

## Best baseline

Of B1 and B2, the one with the higher out-of-fold precision of "coverable" at these operating
points (2022 to 2024). It is not chosen on 2025.

## Promotion of the learner

The learner gets the alias `champion` only if ALL of these hold on the 2025 labels, against the
best baseline:

1. Precision of `coverable` is higher by at least 0.01 (one percentage point), and the 95 %
   bootstrap interval of the difference (resampling months, then requests within them, 2000
   resamples, seed 20261020) excludes zero in the learner's favour.
2. Recall of `coverable` is at least B1's recall on 2025.
3. Hint latency: p95 of the full `hint()` path under 50 ms. This is feature construction from an
   in-memory department snapshot plus the prediction, 1,000 calls after 50 warm-up calls, one
   process. The end-to-end time of `POST /me/leave/check` is reported next to it and is not gated.

If any check fails, the best baseline gets the alias `champion`, and `eval/results/c6.json`, the
model card, the API label, the dashboard and the engine note name the baseline as the served
model. If B1 is the champion the instant hint is exactly the previous stand-in rule.

## Reporting order (fixed)

Every place that reports results (`eval/results/c6.json`, the model card, ADR-015, W13, the engine
note) leads with the **natural-state** result (what each method achieves on realistic states),
then the stress-only result, then the pooled result. Wherever the pooled number is shown it is
labelled "including simulated stress states". Promotion is judged on the pooled 2025 mix because
natural states almost never contain a "no".

## Disagreement with the solver

For every finished M5 check whose month the solver can answer, the hint is compared with the
solver's answer. Disagreement: hint `coverable` while the solver says `coverable_with_trade_off` or
`not_coverable`; or hint `not_coverable` while the solver says `coverable`. Hint `tight` abstains.
`not_applicable` is not scored. Every disagreement is logged (pseudonymous staff id, dates, hint,
solver outcome, versions; no names, no reasons). The solver's answer is what the screen shows.
Situation A is not tuned: if the hint disagrees there, the disagreement is logged and the card
says so.

## Display and truth

- The bundle holds the model text, the thresholds and the feature definitions: no person-level
  value and no staff identifier. Tests check this.
- Staff never see colleagues' names on M5.
- All figures belong to the synthetic data and the simulation only; they are never described as
  outcomes for real staff.
