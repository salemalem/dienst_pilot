"""Fit the C6 candidates (stand-in rule, logistic regression, LightGBM) on 2021 to 2024.

Run ``python -m dienstpilot_ml.training.c6`` (``make train``). The rule is
``ml/leave_surrogate/PROMOTION_RULE.md``; promotion needs the 2025 test and happens in
``eval/run_c6_eval.py``.
"""

import argparse
import contextlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from dienstpilot_ml.features.leave import NUMERIC, ROLES, Matrix
from dienstpilot_ml.leave_surrogate.models import (
    Bundle,
    Vector,
    bundle_sha256,
    design,
    save_bundle,
)
from dienstpilot_ml.training.c6_data import LabelTable, load

REGISTERED_MODEL = "c6-leave-surrogate"
EXPERIMENT = "c6-leave-surrogate"
KINDS = ("stand_in", "logistic", "lightgbm")
CV_YEARS = (2022, 2023, 2024)
C6_VERSION = "0.1.0"
SEED = 20261020
LOGISTIC_L2 = 1.0
GRID = [
    {"num_leaves": nl, "min_child_samples": mc, "n_estimators": ne}
    for nl, mc, ne in product((4, 8), (20, 40), (100, 200))
]
REPO = Path(__file__).resolve().parents[4]
LABELS = REPO / "ml" / "leave_surrogate" / "labels"


# --- metrics ----------------------------------------------------------------------------------
def log_loss(y: Vector, p: Vector) -> float:
    """Return the mean negative log-likelihood."""
    q = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log1p(-q)))


def auc(y: Vector, p: Vector) -> float:
    """Return ROC AUC (ties count one half), from ranks."""
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind="stable")
    ranks = np.empty(len(allv))
    s = allv[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[i : j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    r = np.empty(len(allv))
    r[order] = ranks
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def precision_recall(y: Vector, yes: np.ndarray) -> tuple[float, float]:
    """Return (precision, recall) of the "coverable" hint; precision is 0 with no yes at all."""
    tp = float(np.sum((y == 1) & yes))
    n_yes = float(np.sum(yes))
    n_pos = float(np.sum(y == 1))
    return (tp / n_yes if n_yes else 0.0, tp / n_pos if n_pos else 0.0)


def operating_point(y: Vector, score: Vector, min_recall: float) -> float:
    """Return the threshold with the highest precision among those with recall >= ``min_recall``.

    "Yes" means ``score >= threshold``. Ties in precision go to the lower threshold.
    """
    order = np.argsort(-score, kind="stable")
    s, t = score[order], y[order]
    tp = np.cumsum(t)
    n = np.arange(1, len(s) + 1)
    last_of_value = np.append(s[1:] != s[:-1], True)  # only cut between distinct scores
    recall = tp / max(float(t.sum()), 1.0)
    ok = np.flatnonzero(last_of_value & (recall >= min_recall - 1e-12))
    if len(ok) == 0:
        return float(s.min())
    prec = tp[ok] / n[ok]
    best = ok[np.flatnonzero(prec >= prec.max() - 1e-12)[-1]]  # lowest threshold among the best
    return float(s[best])


# --- models -----------------------------------------------------------------------------------
def fit_logistic(x: Matrix, y: Vector, meta: dict[str, Any]) -> Bundle:
    """Return L2-penalised logistic regression fitted with L-BFGS from zeros (threshold unset)."""
    mean = x[:, 1:].mean(axis=0)
    std = x[:, 1:].std(axis=0)
    std = np.where(std > 0, std, 1.0)
    z = design(x, mean, std)
    k = z.shape[1]

    def loss(w: Vector) -> tuple[float, Vector]:
        p = 1.0 / (1.0 + np.exp(-(z @ w[:k] + w[k])))
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


def fit_lightgbm_text(x: Matrix, y: Vector, point: dict[str, int]) -> str:
    """Return the model text of a LightGBM fitted on (x, y); the role column is categorical."""
    import lightgbm as lgb

    ds = lgb.Dataset(x, label=y, categorical_feature=[0], free_raw_data=False)
    return str(
        lgb.train(lgb_params(point), ds, num_boost_round=point["n_estimators"]).model_to_string()
    )


def stand_in() -> Bundle:
    """Return the previous rule (B1) as a bundle."""
    return Bundle("stand_in", {"model": "stand_in"})


@dataclass
class Candidate:
    """A fitted candidate with its cross-validation record."""

    kind: str
    bundle: Bundle
    cv: dict[str, Any]


def cross_validate(t: LabelTable) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Rolling-origin CV by year (2022 to 2024): OOF scores, the operating points, the record."""
    ys: list[Vector] = []
    xs: list[Matrix] = []
    oof_lin: list[Vector] = []
    oof_gbm: list[list[Vector]] = [[] for _ in GRID]
    yes_b1: list[np.ndarray] = []
    ll_gbm: list[list[float]] = [[] for _ in GRID]
    for year in CV_YEARS:
        tr, te = t.take(t.year < year), t.take(t.year == year)
        ys.append(te.y)
        xs.append(te.x)
        yes_b1.append(stand_in().yes(te.x))
        lin = fit_logistic(tr.x, tr.y, {}).score(te.x)
        oof_lin.append(lin)
        for gi, point in enumerate(GRID):
            raw = Bundle("lightgbm", {}, booster_text=fit_lightgbm_text(tr.x, tr.y, point)).score(
                te.x
            )
            oof_gbm[gi].append(raw)
            ll_gbm[gi].append(log_loss(te.y, raw))
    y = np.concatenate(ys)
    mean_ll = [float(np.mean(v)) for v in ll_gbm]
    best = int(np.argmin(mean_ll))
    p_b1, r_b1 = precision_recall(y, np.concatenate(yes_b1))
    scores = {
        "logistic": np.concatenate(oof_lin),
        "lightgbm": np.concatenate(oof_gbm[best]),
    }
    record: dict[str, dict[str, Any]] = {
        "stand_in": {"oof_precision": p_b1, "oof_recall": r_b1, "n": len(y)}
    }
    thresholds: dict[str, float] = {}
    for kind, s in scores.items():
        thr = operating_point(y, s, r_b1)
        p, r = precision_recall(y, s >= thr)
        thresholds[kind] = thr
        folds = oof_lin if kind == "logistic" else oof_gbm[best]
        record[kind] = {
            "oof_precision": p,
            "oof_recall": r,
            "threshold": thr,
            "oof_auc": auc(y, s),
            "mean_log_loss": float(
                np.mean([log_loss(a, b) for a, b in zip(ys, folds, strict=True)])
            ),
            "n": len(y),
        }
    record["lightgbm"]["grid_point"] = GRID[best]
    record["lightgbm"]["grid_mean_log_loss"] = {
        json.dumps(g, sort_keys=True): v for g, v in zip(GRID, mean_ll, strict=True)
    }
    # The best baseline is chosen here, on 2022-2024, never on 2025.
    best_base = "logistic" if record["logistic"]["oof_precision"] > p_b1 else "stand_in"
    record["best_baseline"] = {"kind": best_base}
    return record, {"best": best, "thresholds": thresholds, "min_recall": r_b1, "y_oof": y}


def train(labels_dir: Path = LABELS) -> tuple[LabelTable, list[Candidate], dict[str, Any]]:
    """Cross-validate and fit all candidates on the training labels (2021 to 2024)."""
    data = load(labels_dir, "train")
    if int(data.year.max()) > 2024:
        raise ValueError("training labels contain 2025")
    cv, oof = cross_validate(data)
    meta = {
        "c6_version": C6_VERSION,
        "train_until": "2024-12-31",
        "labels_sha256": data.sha256,
        "data_manifest_sha256": data.dataset_manifest_sha256,
    }
    point = GRID[oof["best"]]
    lin = fit_logistic(data.x, data.y, meta)
    lin.threshold = oof["thresholds"]["logistic"]
    gbm = Bundle(
        "lightgbm",
        {**meta, "model": "lightgbm", "grid_point": json.dumps(point, sort_keys=True)},
        threshold=oof["thresholds"]["lightgbm"],
        booster_text=fit_lightgbm_text(data.x, data.y, point),
    )
    b1 = stand_in()
    b1.meta = {**meta, "model": "stand_in"}
    bundles = {"stand_in": b1, "logistic": lin, "lightgbm": gbm}
    n_trade = sum(1 for o in data.outcome if o == "coverable_with_trade_off")
    info = {
        "requests_in_training": len(data.y),
        "share_coverable": float(data.y.mean()),
        "trade_off_rows": n_trade,
        "trade_off_share": n_trade / len(data.y),
        "target": "binary: 1 = the solver says plain coverable",
        "min_recall_from_stand_in": oof["min_recall"],
        "features": list(NUMERIC),
        "roles": list(ROLES),
    }
    return data, [Candidate(k, bundles[k], cv[k]) for k in KINDS], {**info, "cv": cv}


def log_to_mlflow(
    store: Path,
    data: LabelTable,
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
                    "labels_sha256": data.sha256,
                    "data_manifest_sha256": data.dataset_manifest_sha256,
                    **tags,
                }
            )
            mlflow.log_params(
                {
                    "train_until": "2024-12-31",
                    **{k: v for k, v in c.bundle.meta.items() if k == "grid_point"},
                }
            )
            for m in ("oof_precision", "oof_recall"):
                mlflow.log_metric(m, c.cv[m])
            out = Path(tmp) / "bundle"
            save_bundle(out, c.bundle)
            mlflow.set_tag("bundle_sha256", bundle_sha256(out))
            mlflow.log_artifacts(str(out), "bundle")
            doc = {
                **c.cv,
                **{k: v for k, v in info.items() if k != "cv"},
                "best_baseline": info["cv"]["best_baseline"],
            }
            (Path(tmp) / "cv.json").write_text(json.dumps(doc, indent=1))
            mlflow.log_artifact(str(Path(tmp) / "cv.json"))
            mv = client.create_model_version(
                REGISTERED_MODEL, source=f"{run.info.artifact_uri}/bundle", run_id=run.info.run_id
            )
            client.set_model_version_tag(REGISTERED_MODEL, mv.version, "kind", c.kind)
            client.set_registered_model_alias(REGISTERED_MODEL, f"candidate-{c.kind}", mv.version)
            versions[c.kind] = int(mv.version)
    return versions


def main() -> None:
    """Parse the arguments and run C6 training."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, default=LABELS)
    ap.add_argument("--store", type=Path, default=REPO / "ml/mlflow")
    args = ap.parse_args()
    data, candidates, info = train(args.labels)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO, check=False
    ).stdout.strip()
    versions = log_to_mlflow(args.store, data, candidates, info, {"git_commit": commit})
    for c in candidates:
        print(
            f"{c.kind:10s} oof precision {c.cv['oof_precision']:.4f}"
            f"  recall {c.cv['oof_recall']:.4f}  registry v{versions[c.kind]}"
        )
    print(f"best baseline (2022-2024): {info['cv']['best_baseline']['kind']}")


if __name__ == "__main__":
    main()
