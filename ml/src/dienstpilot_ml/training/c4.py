"""Fit the C4 candidates (pooled, raw, hierarchical Beta-Binomial) on 2021 to 2024.

Run ``python -m dienstpilot_ml.training.c4`` (``make train``). The rule is
``ml/preference_learner/PROMOTION_RULE.md``; promotion needs the 2025 test and happens in
``eval/run_c4_eval.py``.
"""

import argparse
import contextlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import betaln

from dienstpilot_ml.features.preference import N_CELLS
from dienstpilot_ml.preference_learner.models import (
    P_MAX,
    P_MIN,
    Bundle,
    bundle_sha256,
    save_bundle,
)
from dienstpilot_ml.training.c4_data import (
    AVOID_K,
    AVOID_N,
    WISH_K,
    WISH_N,
    PreferenceData,
    load,
)

REGISTERED_MODEL = "c4-preference-learner"
EXPERIMENT = "c4-preference-learner"
KINDS = ("pooled", "raw", "hierarchical")
TRAIN_END = date(2024, 12, 31)
TEST_END = date(2025, 12, 31)
CV_YEARS = (2022, 2023, 2024)
KAPPA_GRID = np.geomspace(0.5, 2000.0, 60)
LITTLE_HISTORY_WINDOWS = 12
C4_VERSION = "0.1.0"
PROCESSES = (("wish", WISH_K, WISH_N), ("avoid", AVOID_K, AVOID_N))


@dataclass
class Candidate:
    """A fitted candidate with its cross-validation record."""

    kind: str
    bundle: Bundle
    cv: dict[str, Any]


def pooled_rates(people: dict[str, np.ndarray], k_row: int, n_row: int) -> np.ndarray:
    """Return the department rate of every cell: all events over all opportunities."""
    k = sum(c[k_row] for c in people.values())
    n = sum(c[n_row] for c in people.values())
    return np.clip(np.asarray(k) / np.maximum(np.asarray(n), 1.0), P_MIN, P_MAX)


def estimate_kappa(
    people: dict[str, np.ndarray], m: np.ndarray, k_row: int, n_row: int
) -> tuple[float, list[float]]:
    """Return the concentration maximising the beta-binomial marginal likelihood, and the curve."""
    k = np.concatenate([c[k_row] for c in people.values()])
    n = np.concatenate([c[n_row] for c in people.values()])
    mm = np.tile(m, len(people))
    keep = n > 0
    k, n, mm = k[keep], n[keep], mm[keep]
    curve = []
    for kappa in KAPPA_GRID:
        a, b = kappa * mm, kappa * (1.0 - mm)
        curve.append(float(np.sum(betaln(k + a, n - k + b) - betaln(a, b))))
    return float(KAPPA_GRID[int(np.argmax(curve))]), curve


def fit_bundles(people: dict[str, np.ndarray], meta: dict[str, Any]) -> dict[str, Bundle]:
    """Fit the three candidates from per-person counts (the training years summed)."""
    m = {name: pooled_rates(people, kr, nr) for name, kr, nr in PROCESSES}
    kappa = {name: estimate_kappa(people, m[name], kr, nr)[0] for name, kr, nr in PROCESSES}
    return {
        kind: Bundle(
            kind, m["wish"], m["avoid"], kappa["wish"], kappa["avoid"], {**meta, "model": kind}
        )
        for kind in KINDS
    }


def log_likelihood(
    b: Bundle, train: dict[str, np.ndarray], test: dict[str, np.ndarray], process: str
) -> dict[str, tuple[float, float]]:
    """Return per person (log-likelihood, opportunities) of ``test`` under the frozen ``train``."""
    kr, nr = (WISH_K, WISH_N) if process == "wish" else (AVOID_K, AVOID_N)
    zero = np.zeros((4, N_CELLS))
    out: dict[str, tuple[float, float]] = {}
    for staff, t in test.items():
        n_t = t[nr]
        if n_t.sum() == 0:
            continue
        past = train.get(staff, zero)
        p = np.clip(b.predict(process, past[kr], past[nr]), P_MIN, P_MAX)
        ll = float(np.sum(t[kr] * np.log(p) + (n_t - t[kr]) * np.log1p(-p)))
        out[staff] = (ll, float(n_t.sum()))
    return out


def mean_ll(per_person: dict[str, tuple[float, float]]) -> float:
    """Return the mean log-likelihood per opportunity."""
    return sum(v[0] for v in per_person.values()) / sum(v[1] for v in per_person.values())


def cross_validate(data: PreferenceData) -> dict[str, dict[str, Any]]:
    """Rolling-origin CV by year (2022 to 2024): per-fold mean log-likelihood of each kind."""
    record: dict[str, dict[str, Any]] = {k: {"folds": []} for k in KINDS}
    for year in CV_YEARS:
        train = data.upto(year - 1)
        bundles = fit_bundles(train, {})
        test = data.year(year)
        for kind in KINDS:
            fold: dict[str, Any] = {"test_year": year}
            for name, _, _ in PROCESSES:
                fold[f"{name}_mean_ll"] = mean_ll(log_likelihood(bundles[kind], train, test, name))
            fold["kappa_wish"] = bundles[kind].kappa_wish
            fold["kappa_avoid"] = bundles[kind].kappa_avoid
            record[kind]["folds"].append(fold)
    for kind in KINDS:
        folds = record[kind]["folds"]
        for name, _, _ in PROCESSES:
            record[kind][f"mean_{name}_ll"] = float(np.mean([f[f"{name}_mean_ll"] for f in folds]))
        record[kind]["mean_total_ll"] = record[kind]["mean_wish_ll"] + record[kind]["mean_avoid_ll"]
    return record


def train(data_root: Path) -> tuple[PreferenceData, list[Candidate], dict[str, Any]]:
    """Cross-validate and fit all candidates on events up to 2024-12-31."""
    data = load(data_root, through=TRAIN_END)  # 2025 events are physically out of reach here
    cv = cross_validate(data)
    people = data.upto(2024)
    meta = {
        "c4_version": C4_VERSION,
        "train_until": TRAIN_END.isoformat(),
        "data_manifest_sha256": data.manifest_sha256,
    }
    bundles = fit_bundles(people, meta)
    curves = {
        name: estimate_kappa(people, bundles["hierarchical"].prior(name)[0], kr, nr)[1]
        for name, kr, nr in PROCESSES
    }
    info = {
        "people_in_training": len(people),
        "kappa_grid": [float(x) for x in KAPPA_GRID],
        "marginal_log_likelihood": curves,
    }
    return data, [Candidate(k, bundles[k], cv[k]) for k in KINDS], info


def log_to_mlflow(
    store: Path,
    data: PreferenceData,
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
                    "kappa_wish": c.bundle.kappa_wish,
                    "kappa_avoid": c.bundle.kappa_avoid,
                }
            )
            mlflow.log_metric("cv_mean_wish_ll", c.cv["mean_wish_ll"])
            mlflow.log_metric("cv_mean_avoid_ll", c.cv["mean_avoid_ll"])
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
    """Parse the arguments and run C4 training."""
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
            f"{c.kind:13s} cv ll wish {c.cv['mean_wish_ll']:.5f} avoid {c.cv['mean_avoid_ll']:.5f}"
            f"  kappa {c.bundle.kappa_wish:.1f}/{c.bundle.kappa_avoid:.1f}"
            f"  registry v{versions[c.kind]}"
        )


if __name__ == "__main__":
    main()
