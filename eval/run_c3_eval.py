"""Evaluate C3 on the held-out 2025, apply the pre-registered promotion rule, export the champion.

Usage (after ``make train``):
  uv run python eval/run_c3_eval.py   # -> eval/results/c3.json and the champion bundle in ml/

1. Loads the four candidates (trained on 2021 to 2024 only) from the local MLflow registry.
2. Scores them once on 2025 (origins 31 Dec 2024 to 30 Dec 2025, horizons 1 to 42).
3. Applies ml/absence_forecast/PROMOTION_RULE.md, written before any model was fitted.
4. Sets the registry alias ``champion`` and exports that candidate as the serving bundle.
5. Checks how well the forecasts recover the generator's true seasonal pattern (reads the truth).
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "eval" / "results"
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261020

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO, check=False)
    return out.stdout.strip()


def main() -> None:
    """Run the evaluation and write the results."""
    import mlflow
    from mlflow import MlflowClient

    from dienstpilot_eval.c3_truth import recovery
    from dienstpilot_eval.c3_versions import CHAMPION_DIR, RULE, ml_sources_sha256, sha256_file
    from dienstpilot_ml.absence_forecast.models import (
        BUCKETS,
        MU_FLOOR,
        bundle_sha256,
        interval,
        load_bundle,
    )
    from dienstpilot_ml.features.absence import FeatureBuilder
    from dienstpilot_ml.training.cv import TRAIN_END, make_rows
    from dienstpilot_ml.training.data import load
    from dienstpilot_ml.training.metrics import coverage, deviance_terms, mae
    from dienstpilot_ml.training.pipeline import KINDS, REGISTERED_MODEL, TEST_END

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=REPO / "data/synthetic/v1")
    ap.add_argument("--store", type=Path, default=REPO / "ml/mlflow")
    args = ap.parse_args()

    mlflow.set_tracking_uri(f"sqlite:///{args.store / 'mlflow.db'}")
    client = MlflowClient()
    work = Path(tempfile.mkdtemp())
    cands: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        mv = client.get_model_version_by_alias(REGISTERED_MODEL, f"candidate-{kind}")
        bdir = Path(
            mlflow.artifacts.download_artifacts(artifact_uri=mv.source, dst_path=str(work / kind))
        )
        cv = json.loads(
            Path(
                mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="cv.json")
            ).read_text()
        )
        cands[kind] = {
            "version": int(mv.version),
            "dir": bdir,
            "bundle": load_bundle(bdir),
            "cv": cv,
        }

    # --- the held-out 2025 test, scored once ---------------------------------------------------
    ds = load(args.data, through=TEST_END)
    builder = FeatureBuilder(ds.series, ds.calendar, ds.night_shifts)
    first_origin = TRAIN_END  # 31 December 2024: its horizons already point into 2025
    rows = make_rows(builder, ds.series, first_origin, TEST_END - timedelta(days=1), TEST_END)
    hz = [int(h) for h in rows.horizon]
    test: dict[str, dict[str, Any]] = {}
    preds: dict[str, Any] = {}
    for kind, c in cands.items():
        b = c["bundle"]
        mu = np.maximum(b.model.mean(rows.x, builder, rows.origin, hz), MU_FLOOR)
        low, high = interval(mu, rows.horizon, b.quantiles)
        preds[kind] = (mu, low, high)
        buckets = {}
        for lo, hi in BUCKETS:
            m = (rows.horizon >= lo) & (rows.horizon <= hi)
            buckets[f"h{lo}-{hi}"] = {
                "rows": int(m.sum()),
                "mae": mae(rows.y[m], mu[m]),
                "poisson_deviance": float(np.mean(deviance_terms(rows.y[m], mu[m]))),
                "coverage_80": coverage(rows.y[m], low[m], high[m]),
            }
        test[kind] = {
            "rows": len(rows.y),
            "mae": mae(rows.y, mu),
            "poisson_deviance": float(np.mean(deviance_terms(rows.y, mu))),
            "coverage_80": coverage(rows.y, low, high),
            "mean_interval_width": float(np.mean(high - low)),
            "by_horizon": buckets,
        }

    # --- promotion rule (ml/absence_forecast/PROMOTION_RULE.md) -------------------------------
    baselines = [k for k in KINDS if k != "lightgbm"]
    best = min(baselines, key=lambda k: cands[k]["cv"]["mean_poisson_deviance"])
    ch, bl = test["lightgbm"], test[best]
    dev_c, dev_b = (
        deviance_terms(rows.y, preds["lightgbm"][0]),
        deviance_terms(rows.y, preds[best][0]),
    )
    block = np.array([o.toordinal() // 7 for o in rows.origin])
    ids = np.unique(block)
    sums_c = np.array([dev_c[block == i].sum() for i in ids])
    sums_b = np.array([dev_b[block == i].sum() for i in ids])
    counts = np.array([(block == i).sum() for i in ids])
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    diffs = []
    for _ in range(BOOTSTRAP):
        pick = rng.integers(0, len(ids), len(ids))
        diffs.append((sums_c[pick].sum() - sums_b[pick].sum()) / counts[pick].sum())
    ci = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
    dist_c, dist_b = abs(ch["coverage_80"] - 0.8), abs(bl["coverage_80"] - 0.8)
    checks = {
        "deviance_at_least_2pct_lower": {
            "challenger": ch["poisson_deviance"],
            "best_baseline": bl["poisson_deviance"],
            "relative_change": ch["poisson_deviance"] / bl["poisson_deviance"] - 1.0,
            "passed": ch["poisson_deviance"] <= 0.98 * bl["poisson_deviance"],
        },
        "bootstrap_ci_excludes_zero_in_favour": {
            "difference_challenger_minus_baseline_95ci": ci,
            "origin_weeks": len(ids),
            "resamples": BOOTSTRAP,
            "passed": ci[1] < 0.0,
        },
        "mae_not_worse_than_2pct": {
            "challenger": ch["mae"],
            "best_baseline": bl["mae"],
            "relative_change": ch["mae"] / bl["mae"] - 1.0,
            "passed": ch["mae"] <= 1.02 * bl["mae"],
        },
        "coverage_80_in_75_to_85_and_not_3pt_worse": {
            "challenger": ch["coverage_80"],
            "best_baseline": bl["coverage_80"],
            "passed": 0.75 <= ch["coverage_80"] <= 0.85 and dist_c - dist_b <= 0.03,
        },
    }
    promoted = all(v["passed"] for v in checks.values())
    champion = "lightgbm" if promoted else best
    client.set_registered_model_alias(REGISTERED_MODEL, "champion", str(cands[champion]["version"]))

    if CHAMPION_DIR.exists():
        shutil.rmtree(CHAMPION_DIR)
    CHAMPION_DIR.mkdir(parents=True)
    for f in cands[champion]["dir"].iterdir():
        shutil.copy2(f, CHAMPION_DIR / f.name)
    assert bundle_sha256(CHAMPION_DIR) == bundle_sha256(cands[champion]["dir"])
    (CHAMPION_DIR.parent / "champion_registry.json").write_text(
        json.dumps(
            {
                "registered_model": REGISTERED_MODEL,
                "alias": "champion",
                "registry_version": cands[champion]["version"],
                "kind": champion,
            },
            indent=1,
        )
        + "\n"
    )

    # --- recovery of the true seasonal pattern -------------------------------------------------
    realised = {
        ds.series.start + timedelta(days=i): float(v) for i, v in enumerate(ds.series.values)
    }
    test_days = [date(2025, 1, 1) + timedelta(days=i) for i in range(365)]
    forecasts: dict[str, dict[int, dict[date, float]]] = {}
    for kind in KINDS:
        mu = preds[kind][0]
        by_h: dict[int, dict[date, float]] = {h: {} for h in (7, 14, 42)}
        for i, (o, h) in enumerate(zip(rows.origin, hz, strict=True)):
            if h in by_h:
                by_h[h][o + timedelta(days=h)] = float(mu[i])
        forecasts[kind] = by_h
    train_vals = ds.series.values[: (TRAIN_END - ds.series.start).days + 1]
    truth = recovery(args.data, realised, forecasts, float(np.mean(train_vals)), test_days)

    import lightgbm
    import mlflow as _ml
    import statsmodels

    doc = {
        "component": "C3",
        "task": "absent people per day (department level), 1 to 42 days ahead, 80 % interval",
        "champion": {
            "kind": champion,
            "promoted_challenger": promoted,
            "best_baseline_by_cv": best,
            "registry_version": cands[champion]["version"],
            "bundle_sha256": bundle_sha256(CHAMPION_DIR),
        },
        "split": {
            "train_and_cv": "2021-01-01 to 2024-12-31, rolling origin, 6 expanding folds",
            "test": "2025 (origins 2024-12-31 to 2025-12-30), scored once",
            "test_rows": len(rows.y),
        },
        "cv_2022_2024": {k: cands[k]["cv"] for k in KINDS},
        "test_2025": test,
        "promotion": {"rule_file": "ml/absence_forecast/PROMOTION_RULE.md", "checks": checks},
        "truth_recovery": truth,
        "versions": {
            "data": {
                "manifest_sha256": ds.manifest_sha256,
                "seed": ds.seed,
                "generator_version": ds.generator_version,
                "files_read": ds.file_sha256,
            },
            "code": {
                "ml_sources_sha256": ml_sources_sha256(),
                "promotion_rule_sha256": sha256_file(RULE),
                "git_commit_evaluated_on": _git("rev-parse", "HEAD"),
                "working_tree_dirty": bool(_git("status", "--porcelain", "ml", "eval")),
                "python": platform.python_version(),
                "lightgbm": lightgbm.__version__,
                "statsmodels": statsmodels.__version__,
                "mlflow": _ml.__version__,
                "numpy": np.__version__,
            },
        },
    }
    doc["results_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in doc.items() if k != "versions"}, sort_keys=True).encode()
    ).hexdigest()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "c3.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"champion: {champion} (challenger promoted: {promoted}; best baseline {best})")
    for k in KINDS:
        t = test[k]
        print(
            f"  {k:15s} 2025 deviance {t['poisson_deviance']:.4f} mae {t['mae']:.4f}"
            f" cov80 {t['coverage_80']:.3f}"
        )


if __name__ == "__main__":
    main()
