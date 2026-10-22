"""How well does C3 recover the generator's true seasonal pattern? Reads the ground truth.

Only eval/ may read the ground-truth folder (ASSUMPTIONS §14). The true expectation is the
expected number of absent people implied by the generator's own hazard: new episodes per day,
convolved with the episode length (1 + Poisson(2.6) days, at most 21). It ignores two
second-order effects of the simulation (nobody falls sick while on leave, nobody who is already
sick falls sick again), so it is a reference with a small upward bias, not an exact oracle.
The size of that bias is reported next to the results.
"""

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from dienstpilot_ml.features.absence import Matrix
from dienstpilot_ml.training.metrics import deviance_terms, mae


def true_expected_absent(root: Path) -> dict[date, float]:
    """Return the expected number of absent people per day, from the generator's hazard."""
    truth = root / "_truth"
    params = json.loads((truth / "params.json").read_text(encoding="utf-8"))
    lam, cap = float(params["sick_mean_extra_days"]), int(params["sick_max_days"])
    haz = pl.read_parquet(truth / "department_sickness_hazard.parquet").sort("date")
    days = haz["date"].to_list()
    new = haz["expected_new_episodes"].to_numpy()
    # P(episode still running k days after its first day) = P(1 + Poisson(lam) > k), cut at cap.
    pmf = [math.exp(-lam) * lam**j / math.factorial(j) for j in range(cap)]
    surv = [1.0 - sum(pmf[:k]) if k > 0 else 1.0 for k in range(cap)]
    exp = np.convolve(new, np.array(surv))[: len(new)]
    return dict(zip(days, exp.tolist(), strict=True))


def _smooth(v: Matrix, width: int = 28) -> Matrix:
    k = np.ones(width) / width
    return np.convolve(v, k, mode="valid")


def recovery(
    root: Path,
    realised: dict[date, float],
    forecasts: dict[str, dict[int, dict[date, float]]],
    train_mean: float,
    test_days: list[date],
) -> dict[str, Any]:
    """Compare forecasts with the true expectation over the test days.

    ``forecasts[model][horizon][target day]`` is the forecast made ``horizon`` days ahead.
    """
    truth = true_expected_absent(root)
    t = np.array([truth[d] for d in test_days])
    y = np.array([realised[d] for d in test_days])
    const = np.full(len(y), train_mean)
    d_const = float(np.mean(deviance_terms(y, const)))
    d_oracle = float(np.mean(deviance_terms(y, np.maximum(t, 0.05))))
    out: dict[str, Any] = {
        "reference": {
            "definition": "generator hazard convolved with the episode length (c3_truth.py)",
            "mean_true_expected": float(np.mean(t)),
            "mean_realised": float(np.mean(y)),
            "poisson_deviance_vs_realised": d_oracle,
            "mae_vs_realised": mae(y, t),
            "constant_training_mean": {
                "level": train_mean,
                "poisson_deviance_vs_realised": d_const,
                "mae_vs_realised": mae(y, const),
            },
        },
        "models": {},
    }
    winter = [i for i, d in enumerate(test_days) if d.month <= 3]
    for model, by_h in forecasts.items():
        entry: dict[str, Any] = {}
        for h, f in by_h.items():
            days = [d for d in test_days if d in f]
            fv = np.array([f[d] for d in days])
            tv = np.array([truth[d] for d in days])
            yv = np.array([realised[d] for d in days])
            sf, st = _smooth(fv), _smooth(tv)
            peak_f, peak_t = int(np.argmax(sf[: len(winter)])), int(np.argmax(st[: len(winter)]))
            dev = float(np.mean(deviance_terms(yv, np.maximum(fv, 0.05))))
            entry[f"h{h}"] = {
                "days": len(days),
                "corr_daily_with_true": float(np.corrcoef(fv, tv)[0, 1]),
                "corr_28d_smoothed_with_true": float(np.corrcoef(sf, st)[0, 1]),
                "rmse_vs_true": float(np.sqrt(np.mean((fv - tv) ** 2))),
                "winter_peak_day_error_days": peak_f - peak_t,
                "winter_peak_amplitude_ratio": float(sf[peak_f] / st[peak_t]),
                "mean_ratio_forecast_to_true": float(np.mean(fv) / np.mean(tv)),
                "poisson_deviance_vs_realised": dev,
                "share_of_achievable_gain_over_constant": float(
                    (d_const - dev) / (d_const - d_oracle)
                ),
            }
        out["models"][model] = entry
    return out
