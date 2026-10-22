"""Train every C3 candidate with rolling-origin CV, log to MLflow, register the candidates.

Run ``python -m dienstpilot_ml.training`` (``make train``). Promotion to the alias ``champion`` is
not done here: it needs the 2025 test and happens in ``eval/run_c3_eval.py`` by the rule in
``ml/absence_forecast/PROMOTION_RULE.md``.
"""

import contextlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from dienstpilot_ml.absence_forecast.models import (
    MU_FLOOR,
    Bundle,
    MeanModel,
    bundle_sha256,
    conformal_quantiles,
    interval,
    save_bundle,
)
from dienstpilot_ml.features.absence import DailySeries, FeatureBuilder, Matrix
from dienstpilot_ml.training import fit
from dienstpilot_ml.training.cv import (
    CALIBRATION_FOLDS,
    FOLDS,
    TRAIN_END,
    TUNING_FOLDS,
    Rows,
    fold_masks,
    make_rows,
)
from dienstpilot_ml.training.data import Dataset, load
from dienstpilot_ml.training.metrics import coverage, mae, poisson_deviance

REGISTERED_MODEL = "c3-absence-forecaster"
EXPERIMENT = "c3-absence-forecast"
KINDS = ("seasonal_naive", "poisson_glm", "nb_glm", "lightgbm")
TEST_END = date(2025, 12, 31)

Fitter = Callable[[Matrix, Matrix], MeanModel]


@dataclass
class Candidate:
    """A fitted candidate with its cross-validation record."""

    kind: str
    bundle: Bundle
    cv: dict[str, Any]


def _truncate(series: DailySeries, end: date) -> DailySeries:
    n = (end - series.start).days + 1
    return DailySeries(series.start, series.values[:n])


def _oof(
    rows: Rows,
    builder: FeatureBuilder,
    fitter: Fitter | None,
    fixed: MeanModel | None,
    folds: tuple[int, ...],
) -> tuple[Rows, Matrix]:
    """Return the out-of-fold test rows of ``folds`` and the forecasts of the fold models."""
    parts, preds = [], []
    for k in folds:
        train, test = fold_masks(rows, k)
        t = rows.take(test)
        model = fixed if fixed is not None else None
        if model is None:
            assert fitter is not None
            tr = rows.take(train)
            model = fitter(tr.x, tr.y)
        mu = np.maximum(model.mean(t.x, builder, t.origin, [int(h) for h in t.horizon]), MU_FLOOR)
        parts.append(t)
        preds.append(mu)
    merged = Rows(
        np.concatenate([p.x for p in parts]),
        np.concatenate([p.y for p in parts]),
        [o for p in parts for o in p.origin],
        np.concatenate([p.horizon for p in parts]),
    )
    return merged, np.concatenate(preds)


def _cv_record(
    rows: Rows,
    builder: FeatureBuilder,
    fitter: Fitter | None,
    fixed: MeanModel | None,
) -> tuple[dict[str, Any], tuple[float, ...]]:
    """Return the CV summary of one model and its conformal quantiles (from the 2024 folds)."""
    per_fold = []
    for k in range(len(FOLDS)):
        t, mu = _oof(rows, builder, fitter, fixed, (k,))
        per_fold.append(
            {
                "fold": k,
                "origins": [FOLDS[k][0].isoformat(), FOLDS[k][1].isoformat()],
                "rows": len(t.y),
                "poisson_deviance": poisson_deviance(t.y, mu),
                "mae": mae(t.y, mu),
            }
        )
    cal, mu_cal = _oof(rows, builder, fitter, fixed, CALIBRATION_FOLDS)
    q = conformal_quantiles(cal.y, mu_cal, cal.horizon)
    low, high = interval(mu_cal, cal.horizon, q)
    record = {
        "folds": per_fold,
        "mean_poisson_deviance": float(np.mean([f["poisson_deviance"] for f in per_fold])),
        "mean_mae": float(np.mean([f["mae"] for f in per_fold])),
        "calibration_coverage_in_sample": coverage(cal.y, low, high),
        "conformal_quantiles": list(q),
    }
    return record, q


def _tune(rows: Rows, builder: FeatureBuilder) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Pick the LightGBM hyperparameters on the 2022 and 2023 folds only."""
    scores: list[dict[str, Any]] = []
    for hyper in fit.LGBM_GRID:

        def fitter(x: Matrix, y: Matrix, h: dict[str, Any] = hyper) -> MeanModel:
            return fit.fit_lightgbm(x, y, h)

        t, mu = _oof(rows, builder, fitter, None, TUNING_FOLDS)
        scores.append({"hyper": hyper, "poisson_deviance": poisson_deviance(t.y, mu)})
    best = min(scores, key=lambda s: float(s["poisson_deviance"]))
    return dict(best["hyper"]), scores


def _tune_seasonal(
    rows: Rows, builder: FeatureBuilder
) -> tuple[tuple[int, int], list[dict[str, Any]]]:
    """Pick the seasonal-naive window and number of years on all six folds."""
    scores: list[dict[str, Any]] = []
    for window, years in fit.SEASONAL_GRID:
        t, mu = _oof(rows, builder, None, fit.seasonal(window, years), tuple(range(len(FOLDS))))
        scores.append(
            {"window": window, "years": years, "poisson_deviance": poisson_deviance(t.y, mu)}
        )
    best = min(scores, key=lambda s: float(s["poisson_deviance"]))
    return (int(best["window"]), int(best["years"])), scores


def train(data_root: Path) -> tuple[Dataset, list[Candidate], dict[str, Any]]:
    """Cross-validate and fit all candidates on 2021 to 2024 (target dates up to 2024-12-31)."""
    ds = load(data_root, through=TEST_END)
    series = _truncate(ds.series, TRAIN_END)  # 2025 is physically out of reach here
    builder = FeatureBuilder(series, ds.calendar, ds.night_shifts)
    rows = make_rows(builder, series, series.start, TRAIN_END, TRAIN_END)

    (window, years), sn_scores = _tune_seasonal(rows, builder)
    hyper, lgbm_scores = _tune(rows, builder)
    plan: list[tuple[str, Fitter | None, MeanModel | None, dict[str, Any]]] = [
        ("seasonal_naive", None, fit.seasonal(window, years), {"grid": sn_scores}),
        ("poisson_glm", fit.fit_poisson, None, {}),
        ("nb_glm", fit.fit_negative_binomial, None, {}),
        ("lightgbm", lambda x, y: fit.fit_lightgbm(x, y, hyper), None, {"grid": lgbm_scores}),
    ]
    candidates = []
    for kind, fitter, fixed, extra in plan:
        record, q = _cv_record(rows, builder, fitter, fixed)
        record.update(extra)
        model = fixed if fixed is not None else None
        if model is None:
            assert fitter is not None
            model = fitter(rows.x, rows.y)
        meta = {
            "c3_version": "0.1.0",
            "train_until": TRAIN_END.isoformat(),
            "data_manifest_sha256": ds.manifest_sha256,
            "seed": fit.SEED,
        }
        candidates.append(Candidate(kind, Bundle(model, q, meta), record))
    info = {"train_rows": len(rows.y), "seasonal_choice": {"window": window, "years": years}}
    return ds, candidates, info


def log_to_mlflow(
    store: Path,
    ds: Dataset,
    candidates: list[Candidate],
    info: dict[str, Any],
    tags: dict[str, str],
) -> dict[str, int]:
    """Log each candidate as a run, register it, and set the alias ``candidate-<kind>``."""
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")  # nothing leaves this machine
    import mlflow
    from mlflow import MlflowClient

    store.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{store / 'mlflow.db'}")
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        mlflow.create_experiment(EXPERIMENT, artifact_location=(store / "artifacts").as_uri())
    mlflow.set_experiment(EXPERIMENT)
    client = MlflowClient()
    with contextlib.suppress(mlflow.exceptions.MlflowException):  # already registered
        client.create_registered_model(REGISTERED_MODEL)
    versions: dict[str, int] = {}
    for c in candidates:
        with mlflow.start_run(run_name=c.kind) as run, tempfile.TemporaryDirectory() as tmp:
            mlflow.set_tags(
                {
                    "kind": c.kind,
                    "data_manifest_sha256": ds.manifest_sha256,
                    "data_seed": str(ds.seed),
                    "generator_version": ds.generator_version,
                    **tags,
                }
            )
            mlflow.log_params(
                {
                    "train_until": TRAIN_END.isoformat(),
                    "seed": fit.SEED,
                    **{
                        f"p_{k}": json.dumps(v)
                        for k, v in c.bundle.model.params().items()
                        if k != "coef"
                    },
                }
            )
            mlflow.log_metric("cv_mean_poisson_deviance", c.cv["mean_poisson_deviance"])
            mlflow.log_metric("cv_mean_mae", c.cv["mean_mae"])
            for f in c.cv["folds"]:
                mlflow.log_metric("cv_fold_poisson_deviance", f["poisson_deviance"], step=f["fold"])
            out = Path(tmp) / "bundle"
            save_bundle(out, c.bundle)
            mlflow.set_tag("bundle_sha256", bundle_sha256(out))
            mlflow.log_artifacts(str(out), "bundle")
            (Path(tmp) / "cv.json").write_text(json.dumps({**c.cv, **info}, indent=1))
            mlflow.log_artifact(str(Path(tmp) / "cv.json"))
            mv = client.create_model_version(
                REGISTERED_MODEL,
                source=f"{run.info.artifact_uri}/bundle",
                run_id=run.info.run_id,
            )
            client.set_model_version_tag(REGISTERED_MODEL, mv.version, "kind", c.kind)
            client.set_registered_model_alias(REGISTERED_MODEL, f"candidate-{c.kind}", mv.version)
            versions[c.kind] = int(mv.version)
    return versions
