# C4 promotion rule (written before the first model was fitted)

This file was committed before any C4 model was fitted or scored. Its sha256 is recorded in
`eval/results/c4.json`; a test fails if the file changes without the result being regenerated.

## What is modelled

For a person p and a cell c = (weekday, shift type in Frühdienst, Spätdienst, Nachtdienst,
Bereitschaftsdienst), two independent processes, each a Bernoulli outcome per opportunity:

- **Wish process.** Opportunity: a day of that weekday in a request window the person answered,
  excluding days they marked "kann nicht" (Bereitschaftsdienst only on weekends). Success: the
  person wished to work that shift on that day. Wishes that name no shift carry no cell and are
  not used.
- **Avoid process.** Opportunity: a published assignment of the person in that cell, from the
  roster that was published for the month. Success: the person offered that shift for swap
  (accepted or not; an offer shows dislike either way).

## Models

- **B1, pooled:** the department rate of the cell (all people together). No person information.
- **B2, raw:** the person's own rate k / n in the cell; with n = 0 the department rate of the cell.
  No shrinkage.
- **Learner, hierarchical Beta-Binomial:** p_pc ~ Beta(kappa m_c, kappa (1 - m_c)), m_c the pooled
  rate of the cell, kappa one concentration per process estimated by maximising the beta-binomial
  marginal likelihood on the training years over a fixed log-spaced grid of 60 values from 0.5 to
  2000. Prediction is the posterior mean (k + kappa m_c) / (n + kappa).
- Every predicted probability of every model is clipped to [0.001, 0.999] so that the
  log-likelihood is defined.

## Data and splits

- Training and model selection use 2021 to 2024 only. No event dated after 31 December 2024 is
  read by training or cross-validation.
- Rolling-origin cross-validation by calendar year: test years 2022, 2023 and 2024, each trained on
  all earlier years.
- 2025 is the final held-out test. It is scored once, after kappa, the model definitions and this
  rule are frozen. The posterior is frozen at the end of 2024 (it is not updated through 2025), so
  the number describes the evaluated bundle.
- No random splits.

## Metric

Mean Bernoulli log-likelihood per opportunity (nats), computed separately for the wish process and
the avoid process.

## Choosing the best baseline

The best baseline is the one of B1 and B2 with the higher mean log-likelihood in the rolling-origin
cross-validation over 2022 to 2024, summed over both processes. It is not chosen on 2025.

## Promotion of the learner

The learner gets the registry alias `champion` only if ALL of these hold on 2025, for BOTH
processes, against the best baseline:

1. Mean log-likelihood is higher by at least 0.5 % of the absolute value of the baseline's mean
   log-likelihood.
2. The 95 % interval of the log-likelihood difference (bootstrap over people, 2000 resamples,
   fixed seed) excludes zero in the learner's favour.
3. On the little-history group (people with fewer than 12 answered request windows in 2021 to
   2024, including people with none) the learner's mean log-likelihood is not lower than B1's.

If any check fails, the best baseline gets the alias `champion`. `eval/results/c4.json`, the model
card, the API label and the dashboard then name the baseline as the served model. If B1 is the
champion it has no personal signal, so the staff app shows no suggestions and says why.

## Suggestions shown to a person (display policy, not part of promotion)

From the served model's posterior, a cell is suggested ("avoid" from the avoid process, "prefer"
from the wish process) only if all hold: the person has at least 2 events in the cell; the
posterior mean is at least twice the department rate of the cell; and the posterior probability
that the person's rate exceeds the department rate is at least 0.8 (4000 seeded Beta draws). At
most three suggestions are shown, strongest probability first. Suggestions are computed only for a
person who has the setting switched on, and only on their own request.

## Fixed conventions

- Rates in the bundle are department-level only: the pooled rate of each cell and the two
  concentrations. No person-level value and no staff identifier is ever written to the bundle.
- Truth recovery (rank correlation with the generator's latent preferences) is reported in
  `eval/` only and plays no part in promotion.
