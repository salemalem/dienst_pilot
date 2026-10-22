"""Fit the C5 candidates (base rate, logistic regression, LightGBM + isotonic) on 2021 to 2024.

Run ``python -m dienstpilot_ml.training.c5`` (``make train``). The rule is
``ml/cover_ranker/PROMOTION_RULE.md``; promotion needs the 2025 test and happens in
``eval/run_c5_eval.py``.
"""

import argparse
import contextlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from dienstpilot_ml.cover_ranker.models import (
    P_MAX,
    P_MIN,
    Bundle,
    Vector,
    bundle_sha256,
    design,
    fit_isotonic,
    save_bundle,
)
from dienstpilot_ml.features.cover import NUMERIC, SHIFT_TYPES, Matrix
from dienstpilot_ml.training.c5_data import OfferTable, load

REGISTERED_MODEL = "c5-cover-ranker"
EXPERIMENT = "c5-cover-ranker"
KINDS = ("base_rate", "logistic", "lightgbm")
TRAIN_END = date(2024, 12, 31)
TEST_END = date(2025, 12, 31)
CV_YEARS = (2022, 2023, 2024)
C5_VERSION = "0.1.0"
SEED = 20261020
LOGISTIC_L2 = 1.0  # penalty weight on the squared coefficients (not the intercept)
GRID = [
    {"num_leaves": nl, "min_child_samples": mc, "n_estimators": ne}
    for nl, mc, ne in product((4, 8), (20, 40), (100, 200))
]
ECE_BINS = 5


# --- metrics ----------------------------------------------------------------------------------
def brier(y: Vector, p: Vector) -> float:
    """Return the mean squared error of the probabilities."""
    return float(np.mean((p - y) ** 2))


def log_loss(y: Vector, p: Vector) -> float:
    """Return the mean negative log-likelihood."""
    q = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log1p(-q)))


def auc(y: Vector, p: Vector) -> float:
    """Return ROC AUC (ties count one half), from ranks."""
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    order = np.argsort(np.concatenate([pos, neg]), kind="stable")
    allv = np.concatenate([pos, neg])[order]
    ranks = np.empty(len(allv))
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1] == allv[i]:
            j += 1
        ranks[i : j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    r = np.empty(len(allv))
    r[order] = ranks
    rp = r[: len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def ece(y: Vector, p: Vector, bins: int = ECE_BINS) -> float:
    """Return the expected calibration error over equal-frequency bins."""
    order = np.argsort(p, kind="stable")
    total = 0.0
    for idx in np.array_split(order, bins):
        if len(idx):
            total += len(idx) * abs(float(p[idx].mean()) - float(y[idx].mean()))
    return total / len(y)


def reliability(y: Vector, p: Vector, bins: int = ECE_BINS) -> list[dict[str, float]]:
    """Return mean prediction, observed rate and size of each equal-frequency bin."""
    order = np.argsort(p, kind="stable")
    return [
        {"mean_prediction": float(p[i].mean()), "observed_rate": float(y[i].mean()), "n": len(i)}
        for i in np.array_split(order, bins)
        if len(i)
    ]


def scores(y: Vector, p: Vector) -> dict[str, float]:
    """Return the reported metrics of a prediction."""
    return {
        "brier": brier(y, p),
        "auc": auc(y, p),
        "ece": ece(y, p),
        "log_loss": log_loss(y, p),
        "n": float(len(y)),
    }


# --- models -----------------------------------------------------------------------------------
def fit_base_rate(y: Vector, meta: dict[str, Any]) -> Bundle:
    """Return the base-rate model."""
    return Bundle(
        "base_rate", {**meta, "model": "base_rate"}, rate=float(np.clip(y.mean(), P_MIN, P_MAX))
    )


def fit_logistic(x: Matrix, y: Vector, meta: dict[str, Any]) -> Bundle:
    """Return L2-penalised logistic regression fitted with L-BFGS from zeros."""
    mean = x[:, 1:].mean(axis=0)
    std = x[:, 1:].std(axis=0)
    std = np.where(std > 0, std, 1.0)
    z = design(x, mean, std)
    k = z.shape[1]

    def loss(w: Vector) -> tuple[float, Vector]:
        eta = z @ w[:k] + w[k]
        p = 1.0 / (1.0 + np.exp(-eta))
        q = np.clip(p, 1e-12, 1 - 1e-12)
        nll = -np.sum(y * np.log(q) + (1 - y) * np.log1p(-q)) + 0.5 * LOGISTIC_L2 * np.sum(
            w[:k] ** 2
        )
        g = np.empty(k + 1)
        g[:k] = z.T @ (p - y) + LOGISTIC_L2 * w[:k]
        g[k] = np.sum(p - y)
        return float(nll), g

    res = minimize(loss, np.zeros(k + 1), jac=True, method="L-BFGS-B")
    return Bundle(
        "logistic",
        {**meta, "model": "logistic"},
        mean=mean,
        std=std,
        coef=res.x[:k],
        intercept=float(res.x[k]),
    )


def lgb_params(point: dict[str, int]) -> dict[str, Any]:
    """Return the LightGBM parameters of a grid point (see the promotion rule)."""
    return {
        "objective": "binary",
        "learning_rate": 0.05,
        "num_leaves": point["num_leaves"],
        "min_child_samples": point["min_child_samples"],
        "min_data_per_group": 20,
        "cat_smooth": 10.0,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 1,
        "seed": SEED,
        "verbosity": -1,
    }


def fit_lightgbm_raw(x: Matrix, y: Vector, point: dict[str, int]) -> str:
    """Return the model text of a LightGBM fitted on (x, y)."""
    import lightgbm as lgb

    ds = lgb.Dataset(x, label=y, categorical_feature=[0], free_raw_data=False)
    booster = lgb.train(lgb_params(point), ds, num_boost_round=point["n_estimators"])
    return str(booster.model_to_string())


def predict_raw(text: str, x: Matrix) -> Vector:
    """Return uncalibrated LightGBM probabilities."""
    import lightgbm as lgb

    return np.asarray(lgb.Booster(model_str=text).predict(x), dtype=np.float64)


@dataclass
class Candidate:
    """A fitted candidate with its cross-validation record."""

    kind: str
    bundle: Bundle
    cv: dict[str, Any]


def cross_validate(t: OfferTable) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Rolling-origin CV by year (2022 to 2024); returns per-kind records and the OOF cache."""
    record: dict[str, dict[str, Any]] = {k: {"folds": []} for k in KINDS}
    grid_ll: list[list[float]] = [[] for _ in GRID]
    oof_raw: list[list[Vector]] = [[] for _ in GRID]
    oof_y: list[Vector] = []
    for year in CV_YEARS:
        tr, te = t.take(t.year < year), t.take(t.year == year)
        base = fit_base_rate(tr.y, {})
        lin = fit_logistic(tr.x, tr.y, {})
        for kind, p in (("base_rate", base.predict(te.x)), ("logistic", lin.predict(te.x))):
            record[kind]["folds"].append({"test_year": year, **scores(te.y, p)})
        oof_y.append(te.y)
        for gi, point in enumerate(GRID):
            raw = predict_raw(fit_lightgbm_raw(tr.x, tr.y, point), te.x)
            oof_raw[gi].append(raw)
            grid_ll[gi].append(log_loss(te.y, raw))
    mean_ll = [float(np.mean(v)) for v in grid_ll]
    best = int(np.argmin(mean_ll))
    y_oof = np.concatenate(oof_y)
    raw_oof = np.concatenate(oof_raw[best])
    for fi, year in enumerate(CV_YEARS):
        record["lightgbm"]["folds"].append(
            {"test_year": year, **scores(oof_y[fi], oof_raw[best][fi])}
        )
    for kind in KINDS:
        folds = record[kind]["folds"]
        for m in ("brier", "auc", "ece", "log_loss"):
            record[kind][f"mean_{m}"] = float(np.mean([f[m] for f in folds]))
    record["lightgbm"]["grid_point"] = GRID[best]
    record["lightgbm"]["grid_mean_log_loss"] = {
        json.dumps(g, sort_keys=True): v for g, v in zip(GRID, mean_ll, strict=True)
    }
    return record, {"best": best, "raw_oof": raw_oof, "y_oof": y_oof}


def train(data_root: Path) -> tuple[OfferTable, list[Candidate], dict[str, Any]]:
    """Cross-validate and fit all candidates on offers up to 2024-12-31."""
    data = load(data_root, through=TRAIN_END)  # 2025 events are physically out of reach here
    cv, oof = cross_validate(data)
    meta = {
        "c5_version": C5_VERSION,
        "train_until": TRAIN_END.isoformat(),
        "data_manifest_sha256": data.manifest_sha256,
    }
    point = GRID[oof["best"]]
    iso = fit_isotonic(oof["raw_oof"], oof["y_oof"])
    gbm = Bundle(
        "lightgbm",
        {**meta, "model": "lightgbm", "grid_point": json.dumps(point, sort_keys=True)},
        booster_text=fit_lightgbm_raw(data.x, data.y, point),
        calibrator=iso,
    )
    bundles = {
        "base_rate": fit_base_rate(data.y, meta),
        "logistic": fit_logistic(data.x, data.y, meta),
        "lightgbm": gbm,
    }
    info = {
        "offers_in_training": len(data.y),
        "acceptance_rate_in_training": float(data.y.mean()),
        "features": list(NUMERIC),
        "shift_types": list(SHIFT_TYPES),
        "calibrator_steps": len(iso.x),
    }
    return data, [Candidate(k, bundles[k], cv[k]) for k in KINDS], info


def log_to_mlflow(
    store: Path,
    data: OfferTable,
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
                    "data_manifest_sha256": data.manifest_sha256,
                    "data_seed": str(data.seed),
                    "generator_version": data.generator_version,
                    **tags,
                }
            )
            mlflow.log_params(
                {
                    "train_until": TRAIN_END.isoformat(),
                    **{k: v for k, v in c.bundle.meta.items() if k == "grid_point"},
                }
            )
            for m in ("brier", "auc", "ece", "log_loss"):
                mlflow.log_metric(f"cv_mean_{m}", c.cv[f"mean_{m}"])
            out = Path(tmp) / "bundle"
            save_bundle(out, c.bundle)
            mlflow.set_tag("bundle_sha256", bundle_sha256(out))
            mlflow.log_artifacts(str(out), "bundle")
            (Path(tmp) / "cv.json").write_text(json.dumps({**c.cv, **info}, indent=1))
            mlflow.log_artifact(str(Path(tmp) / "cv.json"))
            mv = client.create_model_version(
                REGISTERED_MODEL, source=f"{run.info.artifact_uri}/bundle", run_id=run.info.run_id
            )
            client.set_model_version_tag(REGISTERED_MODEL, mv.version, "kind", c.kind)
            client.set_registered_model_alias(REGISTERED_MODEL, f"candidate-{c.kind}", mv.version)
            versions[c.kind] = int(mv.version)
    return versions


REPO = Path(__file__).resolve().parents[4]


def main() -> None:
    """Parse the arguments and run C5 training."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=REPO / "data/synthetic/v1")
    ap.add_argument("--store", type=Path, default=REPO / "ml/mlflow")
    args = ap.parse_args()
    data, candidates, info = train(args.data)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO, check=False
    ).stdout.strip()
    versions = log_to_mlflow(args.store, data, candidates, info, {"git_commit": commit})
    for c in candidates:
        print(
            f"{c.kind:10s} cv brier {c.cv['mean_brier']:.5f}  auc {c.cv['mean_auc']:.4f}"
            f"  ece {c.cv['mean_ece']:.4f}  registry v{versions[c.kind]}"
        )


if __name__ == "__main__":
    main()
