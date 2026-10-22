# C3 promotion rule (written before the first model was fitted)

This file was committed before any C3 model was trained or scored. Its sha256 is recorded in
`eval/results/c3.json`; a test fails if the file changes without the result being regenerated.

## Data and splits

- Target: number of department staff absent (sick) on a day, day level, 1 to 42 days ahead.
- Training and model selection use 2021 to 2024 only, with expanding-window rolling-origin
  cross-validation (six folds of six months, test origins from 1 January 2022 to 31 December 2024;
  training rows are purged so that no training target lies on or after a fold's first test origin).
- No target date after 31 December 2024 is read by training or cross-validation.
- 2025 is the final held-out test. It is scored once, after the models, their hyperparameters and
  the conformal quantiles are frozen. No random splits anywhere.

## Choosing the best baseline

The best baseline is the baseline (seasonal-naive, Poisson GLM, negative-binomial GLM) with the
lowest mean Poisson deviance in the rolling-origin cross-validation over 2022 to 2024. It is not
chosen on 2025.

## Promotion of the challenger (LightGBM, Poisson objective)

The challenger gets the registry alias `champion` only if ALL of these hold on 2025, against the
best baseline:

1. Mean Poisson deviance is lower by at least 2 % (relative).
2. The 95 % interval of the deviance difference (weekly-block bootstrap over origin weeks, 2000
   resamples, fixed seed) excludes zero in the challenger's favour.
3. MAE is not worse by more than 2 % (relative).
4. Empirical coverage of the 80 % interval is between 75 % and 85 %, and its distance from 80 % is
   not more than 3 percentage points larger than the baseline's.

If any check fails, the best baseline gets the alias `champion`. `eval/results/c3.json`, the model
card and the interface then name the baseline as the served model.

## Fixed conventions

- Forecast means are floored at 0.05 for every model so that the Poisson deviance is defined.
- The nominal interval level is 80 %.
- Hyperparameters of the challenger are tuned on the 2022 and 2023 folds only; conformal
  calibration uses the out-of-fold forecasts of the 2024 folds only.
