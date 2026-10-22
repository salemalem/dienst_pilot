"""Evaluate C4 on the held-out 2025, apply the pre-registered promotion rule, export the champion.

Usage (after ``make train``):
  uv run python eval/run_c4_eval.py   # -> eval/results/c4.json and the champion bundle in ml/

1. Loads the three candidates (fitted on 2021 to 2024 only) from the local MLflow registry.
2. Scores them once on 2025, with the posterior frozen at the end of 2024.
3. Applies ml/preference_learner/PROMOTION_RULE.md, written before any model was fitted.
4. Sets the registry alias ``champion`` and exports that candidate as the serving bundle.
5. Checks how well each model recovers the generator's latent preferences (reads the truth).
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "eval" / "results"
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261020
MARGIN = 0.005  # relative, of the absolute value of the baseline's mean log-likelihood

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO, check=False)
    return out.stdout.strip()


def main() -> None:
    """Run the evaluation and write the results."""
    import mlflow
    import scipy
    from mlflow import MlflowClient

    from dienstpilot_eval.c3_versions import (
        C4_CHAMPION_DIR,
        C4_RULE,
        c4_sources_sha256,
        sha256_file,
    )
    from dienstpilot_eval.c4_truth import recovery
    from dienstpilot_ml.preference_learner.models import bundle_sha256, load_bundle
    from dienstpilot_ml.training.c4 import (
        KINDS,
        LITTLE_HISTORY_WINDOWS,
        PROCESSES,
        REGISTERED_MODEL,
        TEST_END,
        TRAIN_END,
        log_likelihood,
    )
    from dienstpilot_ml.training.c4_data import load

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
    data = load(args.data, through=TEST_END)
    train = data.upto(TRAIN_END.year)
    test = data.year(2025)
    answered = data.answered_until(TRAIN_END.year)
    little = {s for s in test if answered.get(s, 0) < LITTLE_HISTORY_WINDOWS}
    per: dict[str, dict[str, dict[str, tuple[float, float]]]] = {
        kind: {
            name: log_likelihood(cands[kind]["bundle"], train, test, name)
            for name, _, _ in PROCESSES
        }
        for kind in KINDS
    }

    def mean(d: dict[str, tuple[float, float]], who: set[str] | None = None) -> float:
        rows = [v for s, v in d.items() if who is None or s in who]
        return sum(v[0] for v in rows) / sum(v[1] for v in rows)

    test_doc: dict[str, Any] = {}
    for kind in KINDS:
        test_doc[kind] = {
            name: {
                "mean_ll": mean(per[kind][name]),
                "mean_ll_little_history": mean(per[kind][name], little),
                "mean_ll_rest": mean(per[kind][name], set(test) - little),
                "opportunities": sum(v[1] for v in per[kind][name].values()),
                "people": len(per[kind][name]),
            }
            for name, _, _ in PROCESSES
        }

    # --- promotion rule (ml/preference_learner/PROMOTION_RULE.md) -----------------------------
    baselines = ("pooled", "raw")
    best = max(baselines, key=lambda k: cands[k]["cv"]["mean_total_ll"])
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    checks: dict[str, Any] = {}
    for name, _, _ in PROCESSES:
        people = sorted(per["hierarchical"][name])
        delta = np.array([per["hierarchical"][name][s][0] - per[best][name][s][0] for s in people])
        n = np.array([per["hierarchical"][name][s][1] for s in people])
        stats = []
        for _ in range(BOOTSTRAP):
            pick = rng.integers(0, len(people), len(people))
            stats.append(delta[pick].sum() / n[pick].sum())
        ci = [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]
        ll_l, ll_b = test_doc["hierarchical"][name]["mean_ll"], test_doc[best][name]["mean_ll"]
        checks[f"{name}_ll_margin"] = {
            "learner": ll_l,
            "best_baseline": ll_b,
            "difference": ll_l - ll_b,
            "required_difference": MARGIN * abs(ll_b),
            "passed": ll_l - ll_b >= MARGIN * abs(ll_b),
        }
        checks[f"{name}_bootstrap_ci_excludes_zero"] = {
            "difference_95ci": ci,
            "people": len(people),
            "resamples": BOOTSTRAP,
            "passed": ci[0] > 0.0,
        }
        l_l = test_doc["hierarchical"][name]["mean_ll_little_history"]
        l_p = test_doc["pooled"][name]["mean_ll_little_history"]
        checks[f"{name}_little_history_not_below_pooled"] = {
            "learner": l_l,
            "pooled": l_p,
            "people": len(little & set(per["pooled"][name])),
            "passed": l_l >= l_p,
        }
    promoted = all(v["passed"] for v in checks.values())
    champion = "hierarchical" if promoted else best
    client.set_registered_model_alias(REGISTERED_MODEL, "champion", str(cands[champion]["version"]))
    if C4_CHAMPION_DIR.exists():
        shutil.rmtree(C4_CHAMPION_DIR)
    C4_CHAMPION_DIR.mkdir(parents=True)
    for f in cands[champion]["dir"].iterdir():
        shutil.copy2(f, C4_CHAMPION_DIR / f.name)
    assert bundle_sha256(C4_CHAMPION_DIR) == bundle_sha256(cands[champion]["dir"])
    (C4_CHAMPION_DIR.parent / "champion_registry.json").write_text(
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

    # --- recovery of the latent preferences ----------------------------------------------------
    truth = recovery(
        args.data,
        {k: cands[k]["bundle"] for k in KINDS},
        train,
        lambda s: answered.get(s, 0) < LITTLE_HISTORY_WINDOWS,
    )

    doc = {
        "component": "C4",
        "task": "wish and swap-away rates per person x (weekday, shift)",
        "champion": {
            "kind": champion,
            "promoted_learner": promoted,
            "best_baseline_by_cv": best,
            "registry_version": cands[champion]["version"],
            "bundle_sha256": bundle_sha256(C4_CHAMPION_DIR),
        },
        "split": {
            "train_and_cv": "events 2021-01-01 to 2024-12-31, rolling origin by year",
            "test": "2025, scored once, posterior frozen at the end of 2024",
            "little_history_definition": (
                f"fewer than {LITTLE_HISTORY_WINDOWS} answered request windows in 2021 to 2024"
            ),
            "test_people": len(test),
            "test_people_little_history": len(little),
        },
        "cv_2022_2024": {k: cands[k]["cv"] for k in KINDS},
        "test_2025": test_doc,
        "promotion": {"rule_file": "ml/preference_learner/PROMOTION_RULE.md", "checks": checks},
        "truth_recovery": truth,
        "versions": {
            "data": {
                "manifest_sha256": data.manifest_sha256,
                "seed": data.seed,
                "generator_version": data.generator_version,
                "files_read": data.file_sha256,
            },
            "code": {
                "c4_sources_sha256": c4_sources_sha256(),
                "promotion_rule_sha256": sha256_file(C4_RULE),
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
    (RESULTS / "c4.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"champion: {champion} (learner promoted: {promoted}; best baseline {best})")
    for k in KINDS:
        t = test_doc[k]
        print(
            f"  {k:13s} 2025 ll wish {t['wish']['mean_ll']:.5f} avoid {t['avoid']['mean_ll']:.5f}"
        )
    for k, v in checks.items():
        print(f"  {'PASS' if v['passed'] else 'FAIL'} {k}")


if __name__ == "__main__":
    main()
