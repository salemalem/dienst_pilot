# C5 promotion rule and ordering policy (written before any model was fitted)

This file was committed before any C5 model was fitted or scored, and before the 2025 replay was
run. Its sha256 is recorded in `eval/results/c5.json`; a test fails if the file changes without the
result being regenerated.

## What is modelled

One row per **cover offer**: one colleague asked to take one shift of a sick colleague
(`operations/cover_offer`). Label: 1 if the response was `accepted`, 0 for `declined` and
`no_response`. The model estimates P(accept | asked). A cascade stops at the first accept and the
planner asked people in a non-random order, so the rows are not a random sample of all colleagues.
The model card says so; the replay (below) does not depend on it.

## Features (fixed; computed by `ml/src/dienstpilot_ml/features/cover.py`, shared by training and serving)

At the moment the offer is made, for the person asked:

| Feature | Definition |
|---|---|
| `hours_ratio` | credited working hours the person holds in the month of the shift (published roster with swaps and cover applied up to that moment) divided by the month's contract hours (weekly hours / 5 x weekdays of the month) |
| `days_since_last_cover` | days since the person last took a cover, capped at 365 (none: 365) |
| `shifts_last_7d` | working shifts the person holds on the 7 days before the shift's day |
| `notice_hours` | hours from the offer to the start of the shift, limited to 0 to 72 |
| `shift_type` | frueh, spaet, nacht, bereitschaft, ruf |
| `weekday` | weekday of the shift, 0 = Monday |
| `request_hour` | hour of the day of the offer, with minutes as a fraction |
| `confirmed_pref` | the person's own confirmed preferences for that shift type in the 365 days before the offer: the number of `wish_work` entries naming it minus the number of `avoid_shift` entries naming it, limited to -5 to 5 |

`confirmed_pref` uses only what the person entered or confirmed. A preference C4 inferred but the
person did not confirm is never an input. The generated history has `wish_work` entries but no
`avoid_shift` entries (those exist only in the product), so in training the feature can only be
zero or positive.

**Excluded:** age, gender, nationality, family status, absence history, and any person identifier.
No feature is a person-level lookup, so the bundle holds trees and thresholds only.

## Models

- **B1, base rate:** the training acceptance rate for every offer.
- **B2, logistic regression:** the same features, shift type one-hot, numeric features
  standardised with training means and deviations, L2 penalty with fixed strength 1.0 (inverse
  `C` = 1), fitted with L-BFGS from zeros. Not calibrated further.
- **Learner, LightGBM classifier with isotonic calibration.** Binary objective, `learning_rate`
  0.05, `deterministic=True`, `force_row_wise=True`, one thread, `seed=20261020`. The
  hyperparameters come from this fixed grid and are chosen by rolling-origin log-loss (the mean
  over the three folds below): `num_leaves` in {4, 8}, `min_child_samples` in {20, 40},
  `n_estimators` in {100, 200}. Isotonic regression (pool adjacent violators, clipped to the
  training range, output limited to [0.01, 0.99]) is fitted on the out-of-fold predictions of the
  rolling-origin folds, never on 2025. The served model is the LightGBM fitted on all of 2021 to
  2024 with the chosen grid point, followed by that calibrator.
- Isotonic regression and logistic regression are implemented in numpy and scipy in this repo; no
  new dependency is added.

## Data and splits

- Training, model selection and calibration use offers made from 2021-01-01 to 2024-12-31 only.
  No event dated later is read by training or cross-validation.
- Rolling-origin cross-validation by calendar year: test years 2022, 2023, 2024, each trained on
  all earlier years. 2021 has no out-of-fold prediction.
- 2025 is the final held-out test, scored once after the models, the grid and this rule are
  frozen. No random splits.

## Metrics

Brier score (lower is better), ROC AUC (higher is better), and expected calibration error (ECE:
five equal-frequency bins, the weighted mean absolute difference between mean prediction and
observed rate). Log-loss and a reliability table are reported but do not take part in promotion.

## Choosing the best baseline

The best baseline is the one of B1 and B2 with the lower mean Brier score in the rolling-origin
cross-validation over 2022 to 2024. It is not chosen on 2025.

## Promotion of the learner

The learner gets the registry alias `champion` only if ALL of these hold on 2025, against the best
baseline:

1. Brier score is lower by at least 2 % of the baseline's Brier score.
2. The 95 % interval of the Brier difference (bootstrap over cascades, 2000 resamples, fixed seed
   20261020) excludes zero in the learner's favour.
3. ROC AUC is higher than the baseline's and at least 0.55.
4. ECE is at most 0.10.

If any check fails, the best baseline gets the alias `champion`, and `eval/results/c5.json`, the
model card, the API label and the dashboard then name the baseline as the served model. If B1 is
the champion it carries no personal or situational signal: every candidate gets the same
probability and the order inside a bucket falls to the tie-break below.

## Ordering policy (separate from the model, fixed now)

Candidates come from the validator (C2): qualified, rested, within hours. The policy is:

1. **Bucket by cover burden.** Burden is the number of covers the person took in the last 90 days.
   Buckets are two covers wide: 0 to 1, 2 to 3, 4 to 5, and so on (`bucket = covers // 2`). The
   least burdened bucket is asked first.
2. **Inside a bucket** people are ordered by P(accept), highest first. Ties (same probability to
   four decimals) are broken by lower `hours_ratio`, then by pseudonymous staff id.
3. P(accept) never moves a person across a bucket boundary.
4. Each candidate gets a 15-minute window. At most six people are asked, as in the historical
   cascades.

Staff never see their own or anyone else's P(accept).

## Replay of the 2025 sick calls (`eval/run_c5_eval.py`)

The replay asks the question "which ordering closes gaps quickly without always burdening the same
people?". It is a simulation against the generator's behaviour model and says nothing about real
people.

- **Events.** Every sick absence reported in 2025, in report-time order. Each shift the person then
  holds (in the policy's own roster) on the days of the absence, not yet started, opens a cascade,
  as in the product. The roster starts from the published 2025 roster with the swaps of the data
  applied; covers are the policy's own.
- **Pool.** Exactly the product's: the quick filter of `backend/.../app/cover.py` followed by the
  validator (C2) `validate_change` on the month (and the next month in its last week). If this
  proves too slow, the quick filter alone is a fallback only after the user has been told.
- **Acceptance** is drawn from the generator's latent cover model
  (`sigmoid(willingness + 0.4 * affinity - decay * covers in the 30 days before the shift)`, read
  from `_truth/` inside `eval/` only). The covers in that term are the policy's own. Draws are
  common random numbers: for a replicate, the uniform for (shift, person) is the same for every
  policy. A response that takes more than 15 minutes counts as no response (15 minutes pass, the
  next person is asked). Response delays are drawn from 2 to 19 minutes, 20 % of non-accepts are
  no-responses (15 minutes), as in the generator.
- **Policies.**
  - (a) fairness-first with the served champion, buckets two wide, as above;
  - (b) the stand-in ordering: covers in the last 90 days, then `hours_ratio`, then staff id;
  - (c) "ask the most reliable person first": the historical acceptance rate of each person over
    2021 to 2024 offers, smoothed as (accepted + 1) / (asked + 2), highest first, ties by staff id;
  - (a-exact) **pre-registered sensitivity check, not an alternative to choose from afterwards:**
    (a) with exact-count buckets (`bucket = covers`). It is reported next to (a) and the served
    policy stays (a) whatever it shows.
- **Metrics per policy,** each over R = 20 seeded replicates (mean and the range of the middle 95 %
  of replicates; paired differences to (b)): time to fill (minutes from the cascade opening to the
  acceptance, over filled gaps; mean and median), cover-burden Gini (covers taken in 2025 per person,
  over everyone in the department in 2025, people with none counted as zero), escalation rate (share of
  cascades where nobody of the first six accepts, so the Planner must act), people contacted per filled
  gap.
- The numbers belong to the replay only. They are never described as outcomes for real staff.

## Display and truth

- The bundle holds the LightGBM model text, the calibrator steps and the feature definitions: no
  person-level value and no staff identifier. Tests check this.
- Truth recovery (does the model's ordering agree with the latent willingness) is reported in
  `eval/` only and plays no part in promotion.
