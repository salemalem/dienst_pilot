# Model card: C4 Preference Learner (Wunschprofil)

Status: built and evaluated on synthetic data. Nothing here describes a real department, and no number below has been measured on real staff.

## Intended use

Suggest, in the request window, shift preferences a person has probably shown before ("You offered Monday late shifts for swap more often than most. Enter 'rather not late shift' for those days?"). The staff app shows them as dismissible chips (M4) with "Warum? / Why?", which gives the numbers behind each one. A suggestion changes nothing until the person taps to enter it. A confirmed "avoid" chip becomes a soft per-shift preference ("lieber nicht Spätdienst") on each day of that weekday in the open window: the person stays available for every other shift that day, and only the solver's soft objective sees it, with the weight of one unmet wish. A confirmed "prefer" chip becomes ordinary "möchte arbeiten" wishes. Nothing reaches the solver on its own.

## Out-of-scope uses

- Showing a person's inferred preferences to anybody else: the Planner, Oversight, colleagues. They see only what the person confirmed as a wish. An API test walks every endpoint for every persona and fails if inferred values appear anywhere except the person's own `GET /me/wishes`.
- Scoring, ranking or comparing people, or any use in performance or fairness measurement.
- Inferring anything about health, family or other protected attributes. No such field is an input.
- Other departments or real data: it was fitted on one fictional department's synthetic history.

## Data

- Synthetic: `data/synthetic/v1`, fictional "Klinik für Innere Medizin, Klinikum Musterstadt" (`synthdata/ASSUMPTIONS.md`). The exact files read, with a SHA-256 each, are recorded in `eval/results/c4.json`; training re-checks each file against the manifest.
- Tables read: request windows and who answered them, wishes and "kann nicht" entries, published assignments, swap offers. Staff identifiers are pseudonymous UUIDs and live only in memory during training; nothing person-level is written to the bundle. The generator's ground truth is never read by training, and a test fails if code under `ml/` refers to it.
- Training and model selection: 2021 to 2024. Held-out test: 2025. No random splits.

## Events and opportunities (one definition, `ml/src/dienstpilot_ml/features/preference.py`)

A cell is a weekday and one of four shifts (Frühdienst, Spätdienst, Nachtdienst, Bereitschaftsdienst).

- Wish process: a success is a wish for that shift on a day of that weekday. An opportunity is a day of that weekday in a request window the person answered, minus the days they marked "kann nicht" (Bereitschaftsdienst only on weekends). Wishes that name no shift (30 % of them in the generator) carry no cell and are not used.
- Avoid process: a success is a swap offer for a shift in that cell, whether or not a colleague accepted it (an offer shows dislike either way). An opportunity is a published assignment of the person in that cell.
- Approximation: the generator lets a person offer at most one shift a month, so cells are not strictly independent Bernoulli trials; the same approximation is used for every model, so the comparison is fair.

## Models and procedure

- B1, pooled: the department rate of each cell.
- B2, raw: the person's own rate k / n, and the department rate when they have no opportunity. No shrinkage.
- Learner: hierarchical Beta-Binomial per person and cell, p ~ Beta(kappa m, kappa (1 - m)), m the department rate of the cell and one concentration kappa per process, estimated by empirical Bayes (marginal likelihood over a fixed grid, 2021 to 2024). Posterior mean (k + kappa m) / (n + kappa). A person with no history gets the department rate.
- All probabilities are clipped to [0.001, 0.999] so that log-likelihoods are defined.
- Rolling-origin cross-validation by year (test years 2022, 2023, 2024) chooses the best baseline; nothing is chosen on 2025.
- Promotion: the rule in `ml/preference_learner/PROMOTION_RULE.md` was committed before any model was fitted. The learner gets the registry alias `champion` only if, for both processes on 2025, it beats the best baseline by a margin, with a bootstrap interval (over people) that excludes zero, and is not below the pooled baseline for people with little history. Otherwise the best baseline stays champion and every surface says so.
- Suggestions (display policy, also in the rule file): at least 2 events in the cell, a rate at least twice the department's, and a posterior probability of at least 0.8 that the person's rate is above the department's; at most three, computed only on the person's own request and only when they have suggestions switched on (M12). For the raw baseline the probability uses a flat Beta(k + 1, n - k + 1) posterior, an implementation choice the rule leaves open.
- Tracking: local MLflow (`make train`), registered model `c4-preference-learner`. The API serves a committed bundle (`ml/preference_learner/artifacts/champion/bundle.json`) and never imports MLflow or SciPy; tests check that the bundle's hash equals the one in `c4.json` and that it holds only department-level numbers and no staff identifier.

## Results

<!-- c4:start -->
*Generated by `eval/render_tables.py` from `eval/results/c4.json`. Do not edit by hand.*

Data: seed 20261020, generator 1.3.0, manifest `1b5910d6eda6`. Code: C4 sources `a49941494857`, promotion rule `d340a0304a4f`, served bundle `4ce8d6322342` (registry version 2).

Mean log-likelihood per opportunity (nats; higher is better). Cross-validation: rolling origin by year, test years 2022 to 2024. Test: 2025, 30 people with opportunities, posterior frozen at the end of 2024, scored once.

| Model | CV wishes | CV swapped away | 2025 wishes | 2025 swapped away |
|---|---|---|---|---|
| Department rates (baseline B1) | -0.1001 | -0.0820 | -0.1123 | -0.0843 |
| Own rates, no shrinkage (baseline B2) **(served)** | -0.0794 | -0.0736 | -0.0866 | -0.0652 |
| Hierarchical Beta-Binomial (learner) | -0.0777 | -0.0670 | -0.0864 | -0.0633 |

Best baseline by cross-validation (rule step 1): `raw`. Learner promoted: **no**. Promotion checks on 2025, for both processes:

| Process | Check (PROMOTION_RULE.md) | Result | Value |
|---|---|---|---|
| wish | 1. Log-likelihood higher by at least 0.5 % of the baseline's | failed | +0.00014 (needed +0.00043) |
| wish | 2. Bootstrap 95 % interval of the difference excludes zero | failed | [-0.00053, +0.00114] |
| wish | 3. Little-history group not below the pooled baseline | passed | -0.1110 vs -0.1218 |
| avoid | 1. Log-likelihood higher by at least 0.5 % of the baseline's | passed | +0.00194 (needed +0.00033) |
| avoid | 2. Bootstrap 95 % interval of the difference excludes zero | failed | [-0.00062, +0.00522] |
| avoid | 3. Little-history group not below the pooled baseline | passed | -0.0746 vs -0.0848 |

People with little history (fewer than 12 answered request windows in 2021 to 2024): 6 of the 30 test people. 2025 mean log-likelihood by group:

| Model | Little history: wishes | Little history: swapped away | Others: wishes | Others: swapped away |
|---|---|---|---|---|
| Department rates (baseline B1) | -0.1218 | -0.0848 | -0.1101 | -0.0841 |
| Own rates, no shrinkage (baseline B2) | -0.1129 | -0.0764 | -0.0806 | -0.0618 |
| Hierarchical Beta-Binomial (learner) | -0.1110 | -0.0746 | -0.0808 | -0.0598 |

Recovery of the generator's latent preferences (`eval/` only; 23 cells per person, mean Spearman rank correlation per person, 46 people, models fitted on 2021 to 2024; the pooled baseline ranks cells the same way for everybody):

| Model | All people | Others | Little history | Against the pure weekday x shift preference |
|---|---|---|---|---|
| Department rates (baseline B1) | 0.07 | 0.09 | -0.00 | 0.03 |
| Own rates, no shrinkage (baseline B2) | 0.66 | 0.77 | 0.22 | 0.51 |
| Hierarchical Beta-Binomial (learner) | 0.58 | 0.69 | 0.13 | 0.42 |
<!-- c4:end -->

Reading the table (this run; the generated table above is authoritative): both personal models are far ahead of department rates. The hierarchical learner scores slightly higher than raw per-person rates on held-out log-likelihood, but for wishes by less than the pre-registered margin, and for both processes with a bootstrap interval that includes zero, so the rule leaves the raw baseline in service. On recovering the latent preferences, shrinkage did not help here: the raw rates rank a person's cells better than the shrunk estimates, most visibly for people with little history. With about 25 months of wishes per person and a handful of swap offers, the data are thin, but the rule was fixed before the run and not changed afterwards.

## Limitations

- Synthetic data: the latent preferences, the wish noise and the swap behaviour are simulation inputs. Results say that the pipeline works, not that real people reveal their preferences like this.
- Little data per person: about 25 months of wishes and a few dozen swap offers per person over four years. That is why the comparison is sensitive to the margin and interval chosen in the rule; the rule was fixed before the run and not changed afterwards.
- The model sees only what people did, not why. A swap offer may be about a childcare gap or a one-off appointment; the chip says what happened and asks, it does not claim to know.
- A confirmed "avoid" chip is soft and per shift (request-window entry kind `avoid_shift`, ADR-013). It is not counted in the "wishes granted" metrics, and the roster grid does not yet mark whether it was honoured. An earlier version of the staff app wrongly turned such a chip into a hard "kann nicht" for the whole day; that was removed in this phase, and tests pin the soft behaviour.
- The served model is fitted on 2021 to 2024 and is not refitted on 2025, so the published numbers describe exactly the served model. The person's own counts are updated live at request time, from their own tables.
- The truth-recovery check compares learned scores with the generator's liking per cell (`eval/src/dienstpilot_eval/c4_truth.py`). Its target definition and the use of an undivided score (so that the pooled baseline has a department-level ranking instead of an undefined one) were fixed after seeing the first run; this check plays no part in promotion.

## Fairness and privacy considerations

Learned preferences are the person's own: computed per request from their own history, never stored, never returned to the Planner, Oversight or colleagues, and not computed at all when the person switches suggestions off. The bundle holds 28 department rates per process and two concentrations. No protected attribute is an input. Because the model rewards people who state wishes, a person who states few is described less well; the department default then applies, which is neutral rather than penalising. A suggestion never increases or decreases anyone's chance of a shift by itself: only a confirmed wish enters the roster run, where it is a soft preference.

## How to reproduce

```bash
make seed        # generates data/synthetic/v1 if missing
make train       # CV, fits, logs and registers the candidates in ml/mlflow (C3 and C4)
make eval        # scores 2025 once, applies the rule, exports the champion, writes eval/results/c4.json
```
