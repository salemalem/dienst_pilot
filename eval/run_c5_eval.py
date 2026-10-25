"""Evaluate C5 on the held-out 2025, apply the pre-registered promotion rule, replay the sick calls.

Usage (after ``make train``):
  uv run python eval/run_c5_eval.py   # -> eval/results/c5.json and the champion bundle in ml/

1. Loads the three candidates (fitted on 2021 to 2024 only) from the local MLflow registry.
2. Scores them once on the 2025 cover offers.
3. Applies ml/cover_ranker/PROMOTION_RULE.md, written before any model was fitted.
4. Sets the registry alias ``champion`` and exports that candidate as the serving bundle.
5. Replays the 2025 sick calls under four ordering policies (reads the ground truth, eval only).
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "eval" / "results"
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261020
BRIER_MARGIN = 0.02  # relative to the baseline's Brier score
MIN_AUC = 0.55
MAX_ECE = 0.10
REPLICATES = 20

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO, check=False)
    return out.stdout.strip()


def _interval(v: list[float]) -> dict[str, float]:
    a = np.asarray(v, dtype=float)
    return {
        "mean": float(np.nanmean(a)),
        "p2_5": float(np.nanpercentile(a, 2.5)),
        "p97_5": float(np.nanpercentile(a, 97.5)),
    }


def oracle(root: Path, test_year: int) -> dict[str, float]:
    """Return how much signal the generator puts in the offers: AUC of its true P(accept)."""
    import polars as pl

    from dienstpilot_eval.c5_replay import load_latents, p_accept_true
    from dienstpilot_ml.training.c5 import auc

    lat = load_latents(root)
    casc = pl.read_parquet(root / "operations/cover_cascade.parquet")
    off = pl.read_parquet(root / "operations/cover_offer.parquet")
    asg = pl.read_parquet(root / "planning/assignment.parquet")
    what = {
        a: (d, s)
        for a, d, s in zip(
            asg["id"].to_list(), asg["date"].to_list(), asg["shift_type"].to_list(), strict=True
        )
    }
    shift_of = dict(zip(casc["id"].to_list(), casc["assignment_id"].to_list(), strict=True))
    covers: dict[str, list[tuple[Any, Any]]] = defaultdict(list)
    for a, by, closed in zip(
        casc["assignment_id"].to_list(),
        casc["covered_by"].to_list(),
        casc["closed_at"].to_list(),
        strict=True,
    ):
        if by is not None and a in what:
            covers[by].append((what[a][0], closed))
    p, y = [], []
    for r in off.filter(pl.col("asked_at").dt.year() == test_year).iter_rows(named=True):
        day, sh = what[shift_of[r["cascade_id"]]]
        recent = sum(
            1 for d, t in covers[r["staff_id"]] if t < r["asked_at"] and 0 <= (day - d).days <= 30
        )
        p.append(p_accept_true(lat[r["staff_id"]], day, sh, recent))
        y.append(1.0 if r["response"] == "accepted" else 0.0)
    return {"auc_of_true_probability": auc(np.array(y), np.array(p)), "offers": float(len(y))}


def main() -> None:
    """Run the evaluation and write the results."""
    import mlflow
    import scipy
    from mlflow import MlflowClient

    from dienstpilot_eval import c5_replay as replay
    from dienstpilot_eval.c3_versions import (
        C5_CHAMPION_DIR,
        C5_RULE,
        c5_sources_sha256,
        sha256_file,
    )
    from dienstpilot_ml.cover_ranker import policy as pol
    from dienstpilot_ml.cover_ranker.models import bundle_sha256, load_bundle
    from dienstpilot_ml.training.c5 import (
        KINDS,
        REGISTERED_MODEL,
        TEST_END,
        TRAIN_END,
        reliability,
        scores,
    )
    from dienstpilot_ml.training.c5_data import load

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
    table = load(args.data, through=TEST_END)
    test = table.take(table.year == 2025)
    pred = {k: cands[k]["bundle"].predict(test.x) for k in KINDS}
    test_doc = {
        k: {**scores(test.y, pred[k]), "reliability": reliability(test.y, pred[k])} for k in KINDS
    }

    # --- promotion rule (ml/cover_ranker/PROMOTION_RULE.md) ------------------------------------
    best = min(("base_rate", "logistic"), key=lambda k: cands[k]["cv"]["mean_brier"])
    ids = sorted(set(test.cascade))
    index = {c: i for i, c in enumerate(ids)}
    cid = np.array([index[c] for c in test.cascade])
    d_err = (pred["lightgbm"] - test.y) ** 2 - (pred[best] - test.y) ** 2
    num = np.bincount(cid, weights=d_err, minlength=len(ids))
    cnt = np.bincount(cid, minlength=len(ids)).astype(float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    stats = []
    for _ in range(BOOTSTRAP):
        pick = rng.integers(0, len(ids), len(ids))
        stats.append(num[pick].sum() / cnt[pick].sum())
    ci = [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]
    g, b = test_doc["lightgbm"], test_doc[best]
    checks: dict[str, Any] = {
        "brier_margin": {
            "learner": g["brier"],
            "best_baseline": b["brier"],
            "difference": g["brier"] - b["brier"],
            "required_difference": -BRIER_MARGIN * b["brier"],
            "passed": g["brier"] - b["brier"] <= -BRIER_MARGIN * b["brier"],
        },
        "brier_bootstrap_ci_excludes_zero": {
            "difference_95ci": ci,
            "cascades": len(ids),
            "resamples": BOOTSTRAP,
            "passed": ci[1] < 0.0,
        },
        "auc_higher_and_at_least_floor": {
            "learner": g["auc"],
            "best_baseline": b["auc"],
            "floor": MIN_AUC,
            "passed": g["auc"] > b["auc"] and g["auc"] >= MIN_AUC,
        },
        "ece_at_most_ceiling": {
            "learner": g["ece"],
            "ceiling": MAX_ECE,
            "passed": g["ece"] <= MAX_ECE,
        },
    }
    promoted = all(v["passed"] for v in checks.values())
    champion = "lightgbm" if promoted else best
    client.set_registered_model_alias(REGISTERED_MODEL, "champion", str(cands[champion]["version"]))
    if C5_CHAMPION_DIR.exists():
        shutil.rmtree(C5_CHAMPION_DIR)
    C5_CHAMPION_DIR.mkdir(parents=True)
    for f in cands[champion]["dir"].iterdir():
        shutil.copy2(f, C5_CHAMPION_DIR / f.name)
    assert bundle_sha256(C5_CHAMPION_DIR) == bundle_sha256(cands[champion]["dir"])
    (C5_CHAMPION_DIR.parent / "champion_registry.json").write_text(
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

    # --- replay of the 2025 sick calls ---------------------------------------------------------
    world = replay.World(args.data)
    champ = cands[champion]["bundle"]
    rel = world.reliability

    def fairness_first(width: int) -> replay.Orderer:
        return lambda c: pol.order(c, width)

    policies: dict[str, replay.Orderer] = {
        "fairness_first_champion": fairness_first(pol.BUCKET_WIDTH),
        "stand_in": lambda c: sorted(
            c, key=lambda x: (x.covers_last_90_days, x.hours_ratio, x.staff_id)
        ),
        "most_reliable_first": lambda c: sorted(
            c, key=lambda x: (-rel.get(x.staff_id, 0.5), x.staff_id)
        ),
        "fairness_first_exact_buckets_sensitivity": fairness_first(1),
    }
    runs: dict[str, list[dict[str, Any]]] = {k: [] for k in policies}
    for rep in range(REPLICATES):
        for name, order in policies.items():
            m = replay.run(world, order, champ, rep, name)
            runs[name].append(replay.summarise(m, world.population))
    metric_names = [k for k in runs["stand_in"][0] if k != "cascades"]
    replay_doc: dict[str, Any] = {
        "replicates": REPLICATES,
        "sick_call_cascades_per_replicate": {
            k: [r["cascades"] for r in v] for k, v in runs.items()
        },
        "population_for_gini": len(world.population),
        "max_asks": replay.MAX_ASKS,
        "window_minutes": replay.WINDOW_MIN,
        "policies": {
            k: {m: _interval([r[m] for r in v]) for m in metric_names} for k, v in runs.items()
        },
        "paired_difference_to_stand_in": {
            k: {
                m: _interval([a[m] - s[m] for a, s in zip(v, runs["stand_in"], strict=True)])
                for m in metric_names
            }
            for k, v in runs.items()
            if k != "stand_in"
        },
        "note": (
            "Simulation against the generator's behaviour model (reads _truth/, eval only). "
            "Not an outcome for real staff."
        ),
    }

    doc = {
        "component": "C5",
        "task": "P(accept) of a cover offer, and the ordering policy built on it",
        "champion": {
            "kind": champion,
            "promoted_learner": promoted,
            "best_baseline_by_cv": best,
            "registry_version": cands[champion]["version"],
            "bundle_sha256": bundle_sha256(C5_CHAMPION_DIR),
        },
        "split": {
            "train_and_cv": "offers 2021-01-01 to 2024-12-31, rolling origin by year",
            "test": "2025, scored once",
            "test_offers": int(len(test.y)),
            "test_cascades": len(ids),
            "test_acceptance_rate": float(test.y.mean()),
        },
        "cv_2022_2024": {k: {m: v for m, v in cands[k]["cv"].items()} for k in KINDS},
        "test_2025": test_doc,
        "promotion": {"rule_file": "ml/cover_ranker/PROMOTION_RULE.md", "checks": checks},
        "signal_in_the_data": oracle(args.data, 2025),
        "policy": {
            "bucket_width_covers_last_90_days": pol.BUCKET_WIDTH,
            "within_bucket": "P(accept) high to low, ties by lower hours ratio, then staff id",
        },
        "replay_2025": replay_doc,
        "versions": {
            "data": {
                "manifest_sha256": table.manifest_sha256,
                "seed": table.seed,
                "generator_version": table.generator_version,
                "files_read": table.file_sha256,
            },
            "code": {
                "c5_sources_sha256": c5_sources_sha256(),
                "promotion_rule_sha256": sha256_file(C5_RULE),
                "git_commit_evaluated_on": _git("rev-parse", "HEAD"),
                "working_tree_dirty": bool(_git("status", "--porcelain", "ml", "eval")),
                "python": platform.python_version(),
                "scipy": scipy.__version__,
                "mlflow": mlflow.__version__,
                "numpy": np.__version__,
            },
        },
    }
    doc["results_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in doc.items() if k != "versions"}, sort_keys=True).encode()
    ).hexdigest()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "c5.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"champion: {champion} (learner promoted: {promoted}; best baseline {best})")
    for k in KINDS:
        t = test_doc[k]
        print(f"  {k:10s} 2025 brier {t['brier']:.5f} auc {t['auc']:.4f} ece {t['ece']:.4f}")
    for k, v in checks.items():
        print(f"  {'PASS' if v['passed'] else 'FAIL'} {k}")
    for k, v in replay_doc["policies"].items():
        print(
            f"  {k:42s} ttf {v['time_to_fill_mean_min']['mean']:.1f} min"
            f"  gini {v['cover_burden_gini']['mean']:.3f}"
            f"  esc {v['escalation_rate']['mean']:.3f}"
            f"  asks/gap {v['contacted_per_filled_gap']['mean']:.2f}"
        )


if __name__ == "__main__":
    main()
