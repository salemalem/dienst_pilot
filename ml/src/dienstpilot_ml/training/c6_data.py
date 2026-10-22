"""The C6 label tables, read from ``ml/leave_surrogate/labels/`` (never the generator's truth).

Labels are written by ``eval/run_c6_labels.py`` from the product's M5 decision. Training reads the
train file only (2021 to 2024); the test file is read by ``eval/run_c6_eval.py``. Each file is
checked against the hash in ``meta.json`` before it is used.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from dienstpilot_ml.features.leave import LeaveFacts, features, matrix

STRATA = ("natural", "stress")
OUTCOMES = ("coverable", "coverable_with_trade_off", "not_coverable")


@dataclass(frozen=True)
class LabelTable:
    """Every labelled request of one split, with features and the binary target."""

    x: np.ndarray  # (n, len(FEATURES))
    y: np.ndarray  # 1 if the solver says plain "coverable", else 0
    outcome: list[str]
    month: list[date]
    stratum: list[str]
    year: np.ndarray
    sha256: str
    dataset_manifest_sha256: str

    def take(self, mask: np.ndarray) -> "LabelTable":
        """Return the rows where ``mask`` is true."""
        idx = np.flatnonzero(mask)
        return LabelTable(
            self.x[idx],
            self.y[idx],
            [self.outcome[i] for i in idx],
            [self.month[i] for i in idx],
            [self.stratum[i] for i in idx],
            self.year[idx],
            self.sha256,
            self.dataset_manifest_sha256,
        )


def load(labels_dir: Path, split: str) -> LabelTable:
    """Read ``<split>.jsonl`` after checking its hash against ``meta.json``."""
    path = labels_dir / f"{split}.jsonl"
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    meta = json.loads((labels_dir / "meta.json").read_text(encoding="utf-8"))
    if meta["files"][f"{split}.jsonl"] != sha:
        raise ValueError(f"{path.name} differs from the hash in meta.json: regenerate or reseal")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    x = matrix(features(LeaveFacts.from_json(r["facts"])) for r in rows)
    months = [date.fromisoformat(r["month"]) for r in rows]
    return LabelTable(
        x,
        np.array([r["outcome"] == "coverable" for r in rows], dtype=np.float64),
        [r["outcome"] for r in rows],
        months,
        [r["stratum"] for r in rows],
        np.array([m.year for m in months]),
        sha,
        meta["dataset_manifest_sha256"],
    )
