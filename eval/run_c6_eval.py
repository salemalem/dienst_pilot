"""Evaluate C6 on the held-out 2025 labels and apply the pre-registered promotion rule.

Usage (after ``make labels`` and ``make train``):
  uv run python eval/run_c6_eval.py   # -> eval/results/c6.json and the champion bundle in ml/

1. Loads the three candidates (fitted on 2021 to 2024 only) from the local MLflow registry.
2. Scores them once on the 2025 labels, naturally drawn states first, then stress states, then
   the pooled mix (labelled "including simulated stress states").
3. Applies ml/leave_surrogate/PROMOTION_RULE.md, written before any label or model existed.
4. Sets the registry alias ``champion`` and exports that candidate as the serving bundle.
5. Measures the latency of the full hint path and the agreement of the hint with the solver.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "eval" / "results"
LABELS = REPO / "ml" / "leave_surrogate" / "labels"
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261020
PRECISION_MARGIN = 0.01
LATENCY_P95_MS = 50.0
LATENCY_CALLS = 1000
LATENCY_WARMUP = 50
POOLED = "pooled including simulated stress states"

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO, check=False)
    return out.stdout.strip()


def _cell(y: np.ndarray, yes: np.ndarray, outcome: list[str]) -> dict[str, Any]:
    """Precision and recall of a yes, with what the false yes were."""
    tp = int(np.sum((y == 1) & yes))
    n_yes = int(np.sum(yes))
    n_pos = int(np.sum(y == 1))
    false_yes = [o for o, v, t in zip(outcome, yes, y, strict=True) if v and t == 0]
    return {
        "n": int(len(y)),
        "coverable_by_solver": n_pos,
        "yes": n_yes,
        "true_yes": tp,
        "false_yes": n_yes - tp,
        "false_yes_trade_off": sum(1 for o in false_yes if o == "coverable_with_trade_off"),
        "false_yes_not_coverable": sum(1 for o in false_yes if o == "not_coverable"),
        "precision": tp / n_yes if n_yes else None,
        "recall": tp / n_pos if n_pos else None,
    }


def _by_stratum(test: Any, yes: np.ndarray) -> dict[str, Any]:
    """Natural states first, then stress states, then the pooled mix."""
    out: dict[str, Any] = {}
    for s in ("natural", "stress"):
        m = np.array([x == s for x in test.stratum])
        out[s] = _cell(test.y[m], yes[m], [o for o, k in zip(test.outcome, m, strict=True) if k])
    out["pooled"] = _cell(test.y, yes, test.outcome)
    out["pooled_label"] = POOLED
    return out


def _precision(y: np.ndarray, yes: np.ndarray) -> float:
    n = yes.sum()
    return float((y[yes] == 1).sum() / n) if n else 0.0


def _bootstrap(test: Any, yes_a: np.ndarray, yes_b: np.ndarray) -> list[float]:
    """95 % interval of precision(a) - precision(b): resample months, then requests in them."""
    months = sorted(set(test.month))
    by = {m: np.flatnonzero([x == m for x in test.month]) for m in months}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    diffs = []
    for _ in range(BOOTSTRAP):
        idx = np.concatenate(
            [rng.choice(by[months[i]], len(by[months[i]])) for i in rng.integers(0, len(months), len(months))]
        )
        diffs.append(_precision(test.y[idx], yes_a[idx]) - _precision(test.y[idx], yes_b[idx]))
    return [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]


def _agreement(test: Any, hints: list[str]) -> dict[str, Any]:
    """How often the hint agrees with the solver (abstains when the hint is "tight")."""
    from dienstpilot.app.jobs import hint_agreement

    out: dict[str, Any] = {}
    for name, mask in (
        ("natural", [s == "natural" for s in test.stratum]),
        ("stress", [s == "stress" for s in test.stratum]),
        (POOLED, [True] * len(test.stratum)),
    ):
        c = {"agree": 0, "disagree": 0, "abstain": 0}
        shown = {"coverable": 0, "tight": 0, "not_coverable": 0}
        for h, o, k in zip(hints, test.outcome, mask, strict=True):
            if k:
                c[hint_agreement(h, o)] += 1
                shown[h] += 1
        n = sum(c.values())
        out[name] = {**c, "n": n, "agreement_rate": c["agree"] / n if n else None, "hints": shown}
    return out


def _latency(bundle: Any, world: Any, specs: list[Any]) -> dict[str, Any]:
    """Time the full hint path: facts from the department state, features, prediction."""
    from dienstpilot_eval.c6_labels import draw
    from dienstpilot_ml.features.leave import build_facts, features, matrix

    args = [draw(world, s).facts_args for s in specs]
    pick = [args[i % len(args)] for i in range(LATENCY_WARMUP + LATENCY_CALLS)]
    ms: list[float] = []
    for i, a in enumerate(pick):
        t0 = time.perf_counter()
        bundle.hint(matrix([features(build_facts(**a))]))
        if i >= LATENCY_WARMUP:
            ms.append((time.perf_counter() - t0) * 1000)
    a_ = np.asarray(ms)
    return {
        "calls": len(ms),
        "warmup_calls": LATENCY_WARMUP,
        "p50_ms": float(np.percentile(a_, 50)),
        "p95_ms": float(np.percentile(a_, 95)),
        "max_ms": float(a_.max()),
        "what": "build_facts + features + prediction, one process, one thread",
    }


def main() -> None:
    """Run the evaluation and write the results."""
    import mlflow
    import scipy
    from mlflow import MlflowClient

    from dienstpilot_eval.c3_versions import (
        C6_CHAMPION_DIR,
        C6_RULE,
        c6_sources_sha256,
        sha256_file,
    )
    from dienstpilot_eval.c6_labels import World, specs
    from dienstpilot_ml.leave_surrogate.models import bundle_sha256, load_bundle
    from dienstpilot_ml.training.c6 import KINDS, REGISTERED_MODEL, auc
    from dienstpilot_ml.training.c6_data import load

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
        bdir = Path(mlflow.artifacts.download_artifacts(artifact_uri=mv.source, dst_path=str(work / kind)))
        cv = json.loads(
            Path(mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="cv.json")).read_text()
        )
        cands[kind] = {"version": int(mv.version), "dir": bdir, "bundle": load_bundle(bdir), "cv": cv}

    # --- the held-out 2025 test, scored once ---------------------------------------------------
    test = load(LABELS, "test")
    if int(test.year.min()) != 2025 or int(test.year.max()) != 2025:
        raise SystemExit("the test labels are not 2025 only")
    yes = {k: np.asarray(cands[k]["bundle"].yes(test.x)) for k in KINDS}
    test_doc = {k: _by_stratum(test, yes[k]) for k in KINDS}
    # Reported only, not eligible: the old rule if it also counted pending requests.
    pend = _col("pending_max")
    test_doc["stand_in_counting_pending_sensitivity"] = _by_stratum(
        test, (np.maximum(test.x[:, _col("approved_max")], test.x[:, pend]) <= 4)
    )

    # --- promotion rule (ml/leave_surrogate/PROMOTION_RULE.md) ---------------------------------
    best = cands["stand_in"]["cv"]["best_baseline"]["kind"]
    ci = _bootstrap(test, yes["lightgbm"], yes[best])
    p_l = test_doc["lightgbm"]["pooled"]["precision"] or 0.0
    p_b = test_doc[best]["pooled"]["precision"] or 0.0
    r_l = test_doc["lightgbm"]["pooled"]["recall"] or 0.0
    r_s = test_doc["stand_in"]["pooled"]["recall"] or 0.0
    world = World(args.data)
    lat = {k: _latency(cands[k]["bundle"], world, specs("test")) for k in KINDS}
    checks: dict[str, Any] = {
        "precision_higher_by_margin_and_ci_excludes_zero": {
            "learner": p_l,
            "best_baseline": p_b,
            "difference": p_l - p_b,
            "required_difference": PRECISION_MARGIN,
            "difference_95ci": ci,
            "resamples": BOOTSTRAP,
            "passed": p_l - p_b >= PRECISION_MARGIN and ci[0] > 0.0,
        },
        "recall_at_least_stand_in": {
            "learner": r_l,
            "stand_in": r_s,
            "passed": r_l >= r_s,
        },
        "hint_latency_p95_under_limit": {
            "learner_p95_ms": lat["lightgbm"]["p95_ms"],
            "limit_ms": LATENCY_P95_MS,
            "passed": lat["lightgbm"]["p95_ms"] < LATENCY_P95_MS,
        },
    }
    promoted = all(v["passed"] for v in checks.values())
    champion = "lightgbm" if promoted else best
    client.set_registered_model_alias(REGISTERED_MODEL, "champion", str(cands[champion]["version"]))
    if C6_CHAMPION_DIR.exists():
        shutil.rmtree(C6_CHAMPION_DIR)
    C6_CHAMPION_DIR.mkdir(parents=True)
    for f in cands[champion]["dir"].iterdir():
        shutil.copy2(f, C6_CHAMPION_DIR / f.name)
    assert bundle_sha256(C6_CHAMPION_DIR) == bundle_sha256(cands[champion]["dir"])
    (C6_CHAMPION_DIR.parent / "champion_registry.json").write_text(
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

    # --- agreement of the served hint with the solver ------------------------------------------
    hints = cands[champion]["bundle"].hint(test.x)
    meta = json.loads((LABELS / "meta.json").read_text(encoding="utf-8"))
    fid_path = LABELS / "fidelity.json"
    fidelity = (
        json.loads(fid_path.read_text(encoding="utf-8"))
        if fid_path.exists()
        else {"note": "not measured yet (eval/run_c6_labels.py --fidelity 200)"}
    )
    api_path = RESULTS / "c6_endpoint_latency.json"
    endpoint = (
        json.loads(api_path.read_text(encoding="utf-8"))
        if api_path.exists()
        else {"note": "not measured (eval/run_c6_endpoint_latency.py needs the running API)"}
    )
    train_cv = cands["stand_in"]["cv"]
    doc: dict[str, Any] = {
        "component": "C6",
        "task": "Will the solver answer plain 'coverable' for this leave request? (instant hint)",
        "reporting_order": ["natural", "stress", "pooled"],
        "reporting_note": "Every report leads with the natural states, then the stress states, then "
        "the pooled mix, which is labelled: including simulated stress states. (JSON keys are sorted; "
        "this list is the order of display.)",
        "champion": {
            "kind": champion,
            "promoted_learner": promoted,
            "best_baseline_by_cv": best,
            "registry_version": cands[champion]["version"],
            "bundle_sha256": bundle_sha256(C6_CHAMPION_DIR),
        },
        "target": {
            "kind": "binary",
            "definition": "1 = the solver says plain coverable; 0 = coverable with a trade-off or not coverable",
            "rule": "binary if coverable_with_trade_off is under 5 % of training rows or under 100 rows",
            "training_trade_off_rows": train_cv["trade_off_rows"],
            "training_trade_off_share": train_cv["trade_off_share"],
        },
        "labels": {
            "protocol": "ml/leave_surrogate/PROMOTION_RULE.md",
            "summary": meta["summary"],
            "versions": meta["versions"],
            "files_sha256": meta["files"],
            "fidelity_check": fidelity,
            "stress_note": "Stress states are counterfactual pile-ups; the planner's own rule caps real "
            "states at 6 concurrent, so natural states almost never contain a 'no'.",
        },
        "cv_2022_2024": {k: cands[k]["cv"] for k in KINDS},
        "test_2025": test_doc,
        "test_auc_pooled": {k: auc(test.y, cands[k]["bundle"].score(test.x)) for k in ("logistic", "lightgbm")},
        "promotion": {"rule_file": "ml/leave_surrogate/PROMOTION_RULE.md", "checks": checks},
        "latency_full_hint_path": lat,
        "latency_endpoint_end_to_end": endpoint,
        "agreement_with_solver_2025": _agreement(test, list(hints)),
        "versions": {
            "data": {"labels_dataset_manifest_sha256": meta["dataset_manifest_sha256"]},
            "code": {
                "c6_sources_sha256": c6_sources_sha256(),
                "promotion_rule_sha256": sha256_file(C6_RULE),
                "git_commit_evaluated_on": _git("rev-parse", "HEAD"),
                "working_tree_dirty": bool(_git("status", "--porcelain", "ml", "eval")),
                "python": platform.python_version(),
                "scipy": scipy.__version__,
                "mlflow": mlflow.__version__,
                "numpy": np.__version__,
            },
        },
        "limitations": [
            "Labels are the solver's answers for simulated requests on synthetic data; stress states are "
            "counterfactual. Precision depends on the share of stress states (fixed at 50 %).",
            "Latency is wall-clock on the machine that ran the evaluation and is not reproducible.",
        ],
    }
    # The results hash covers the reproducible numbers (not the wall-clock latency or the versions).
    stable = {k: v for k, v in doc.items() if k not in ("versions", "latency_full_hint_path", "latency_endpoint_end_to_end")}
    stable["promotion"] = {
        "rule_file": doc["promotion"]["rule_file"],
        "checks": {k: {a: b for a, b in v.items() if "ms" not in a} for k, v in checks.items()},
    }
    doc["results_sha256"] = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "c6.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"champion: {champion} (learner promoted: {promoted}; best baseline {best})")
    for k in (*KINDS, "stand_in_counting_pending_sensitivity"):
        t = test_doc[k]
        print(
            f"  {k:40s} natural P {t['natural']['precision']}  stress P {t['stress']['precision']}"
            f"  pooled P {t['pooled']['precision']} R {t['pooled']['recall']}"
        )
    for k, v in checks.items():
        print(f"  {'PASS' if v['passed'] else 'FAIL'} {k}")


def _col(name: str) -> int:
    from dienstpilot_ml.features.leave import FEATURES

    return FEATURES.index(name)


if __name__ == "__main__":
    main()
