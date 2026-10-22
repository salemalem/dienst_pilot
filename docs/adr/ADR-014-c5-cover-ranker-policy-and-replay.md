# ADR-014: C5 cover ranker, policy kept apart from the model, and a replay against the generator

- Status: Accepted
- Date: 2026-10-22
- Phase: 8c (C5 cover acceptance ranker)
- Builds on: ADR-012, ADR-013

## Context

C5 orders colleagues for a cover request. Two things pull in different directions: closing a gap quickly (ask whoever is likely to say yes) and not always burdening the same willing people (fairness). A model alone would favour the first; ARCHITECTURE §9 puts the second in a policy and leaves the model only an ordering role inside it.

## Decision

1. **Same convention as C3 and C4.** `ml/cover_ranker/PROMOTION_RULE.md` was committed before any model was fitted and before the replay was run; its hash is recorded in `eval/results/c5.json`, and a test fails if it changes afterwards. The rule also fixes the bucket width, the tie-break, the replay protocol and its sensitivity check. The best baseline (base rate or logistic regression) is chosen on 2022 to 2024 cross-validation; the LightGBM learner is judged once on 2025. The first run did not pass, so the base rate is served.
2. **Policy separate from the model** (`ml/src/dienstpilot_ml/cover_ranker/policy.py`). Candidates come from C2. Buckets are two covers wide on the 90-day cover count, least burdened first; P(accept) orders only inside a bucket; ties go to lower hours against contract, then the staff id. A property test shows a probability never moves a person across a bucket.
3. **P(accept) never leaves the ranker.** The port returns the candidates in order; there is no probability field, and a privacy test walks every GET endpoint for every persona for keys such as `p_accept`. The Planner sees names in order (W7, W7b, the cover view); staff see nothing about order or probability.
4. **The port carries the situation.** `CoverCandidate` gains the model's inputs with defaults; the application layer fills them with the shared definitions of `dienstpilot_ml.features.cover`, the same module training uses (one feature module, no train/serve skew). The tie-break hours ratio now follows the rule's definition (credited hours over weekly hours / 5 per weekday), not the earlier leave-aware figure.
5. **Only confirmed preferences are an input.** The feature counts the person's own `wish_work` and `avoid_shift` entries for a shift type. Nothing C4 inferred and the person did not confirm enters C5. Age, gender, nationality, family status and absence history are excluded, and no person identifier is a feature, so the bundle (LightGBM trees, calibrator steps, feature list) holds no person-level value; tests check keys, UUID-like values and the dataset's staff ids.
6. **No new dependencies.** Isotonic regression (pool adjacent violators) and L2 logistic regression (L-BFGS) are implemented with numpy and scipy, which the `train` extra already has. Serving needs numpy and LightGBM; an import-linter contract extends to `dienstpilot_ml.cover_ranker`.
7. **The replay lives in `eval/` and reads the ground truth.** `eval/src/dienstpilot_eval/c5_replay.py` replays every 2025 sick report in report-time order. The pool is the product's: the quick filter of `app/cover.py`, re-implemented in `eval/`, then the same validator (C2) `validate_change`. Acceptance is the generator's latent model with common random numbers across policies, so differences come from the ordering. It reports time to fill, cover-burden Gini, escalation rate and people asked per filled gap over 20 replicates, and the exact-burden bucketing as a sensitivity check fixed in advance. It is a simulation against the generator's behaviour model and is described as such everywhere.
8. **The stand-in is removed from the registry**, replaced by `C5CoverRanker`. Its ordering survives only as policy (b) in the replay.

## Consequences

- The served champion has no situational signal, so inside a bucket the order is by hours against contract. The policy with the champion is then not distinguishable from the old stand-in in the replay, and the card says so rather than rewording it.
- The C5 source hash is separate from C3's and C4's: `ml_sources_sha256` and `c4_sources_sha256` exclude `cover_ranker/`, `features/cover.py` and `training/c5*`, so adding C5 did not invalidate `c3.json` or `c4.json`.
- A later model with person-level signal would raise the question whether ordering by willingness inside a bucket reintroduces the burden concentration the policy is there to limit. The bucket width is the control, and it would be re-registered, not tuned after the fact.
- Situation C is unchanged: Dr. Alvarez is asked first, through the tie-break in burden bucket 0. If a future champion reorders that bucket, the story gets updated instead of the model or the data.
