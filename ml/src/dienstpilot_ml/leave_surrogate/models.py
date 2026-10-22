"""C6 models: the stand-in rule, logistic regression, and LightGBM, as served bundles.

A bundle holds model parameters, the two thresholds of the hint and the feature definitions;
never a person-level value or a staff identifier. Serving needs numpy and lightgbm; training adds
scipy. The score is P(coverable), the probability that the solver will answer plain "coverable".
"""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from dienstpilot_ml.features.leave import FEATURES, NUMERIC, ROLES, Matrix

FORMAT = "c6-bundle-1"
KINDS = ("stand_in", "logistic", "lightgbm")
BUNDLE_FILE = "bundle.json"
MODEL_FILE = "model.txt"
P_NOT = 0.10  # below this the hint is "not coverable" (fixed in the rule, not part of promotion)
STAND_IN_LIMIT = 6  # concurrent approved leave the department plans with (ASSUMPTIONS §11)
P_MIN, P_MAX = 0.001, 0.999
Vector = NDArray[np.float64]
APPROVED_MAX = FEATURES.index("approved_max")


def design(x: Matrix, mean: Vector, std: Vector) -> Matrix:
    """Return the logistic design matrix: standardised numeric columns and one-hot role."""
    z = (x[:, 1:] - mean) / std
    onehot = np.zeros((len(x), len(ROLES)))
    onehot[np.arange(len(x)), x[:, 0].astype(int)] = 1.0
    return np.hstack([z, onehot])


@dataclass
class Bundle:
    """One C6 model with everything needed to give the hint."""

    kind: str
    meta: dict[str, Any]
    threshold: float = 0.5  # P(coverable) at or above this: hint "coverable"
    mean: Vector = field(default_factory=lambda: np.zeros(len(NUMERIC)))  # logistic
    std: Vector = field(default_factory=lambda: np.ones(len(NUMERIC)))
    coef: Vector = field(default_factory=lambda: np.zeros(len(NUMERIC) + len(ROLES)))
    intercept: float = 0.0
    booster_text: str = ""  # lightgbm
    _booster: Any = None

    def score(self, x: Matrix) -> Vector:
        """Return P(coverable) per row (columns in ``FEATURES`` order); the rule has no score."""
        if self.kind == "stand_in":
            raise ValueError("the stand-in rule has no probability")
        if self.kind == "logistic":
            z = design(x, self.mean, self.std) @ self.coef + self.intercept
            return np.clip(1.0 / (1.0 + np.exp(-z)), P_MIN, P_MAX)
        if self._booster is None:
            import lightgbm as lgb

            self._booster = lgb.Booster(model_str=self.booster_text)
        return np.clip(np.asarray(self._booster.predict(x), dtype=np.float64), P_MIN, P_MAX)

    def yes(self, x: Matrix) -> NDArray[np.bool_]:
        """Return whether the hint is "coverable" per row."""
        if self.kind == "stand_in":
            return np.asarray(x[:, APPROVED_MAX] <= STAND_IN_LIMIT - 2)
        return np.asarray(self.score(x) >= self.threshold)

    def hint(self, x: Matrix) -> list[str]:
        """Return the hint per row: ``coverable``, ``tight`` or ``not_coverable``."""
        if self.kind == "stand_in":
            worst = x[:, APPROVED_MAX]
            return [
                "not_coverable"
                if w >= STAND_IN_LIMIT
                else "tight"
                if w >= STAND_IN_LIMIT - 1
                else "coverable"
                for w in worst
            ]
        p = self.score(x)
        return [
            "coverable" if v >= self.threshold else "not_coverable" if v < P_NOT else "tight"
            for v in p
        ]


def _canonical(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def save_bundle(path: Path, b: Bundle) -> None:
    """Write bundle.json (and model.txt for LightGBM) into ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "format": FORMAT,
        "kind": b.kind,
        "features": list(FEATURES),
        "roles": list(ROLES),
        "p_not_coverable_below": P_NOT,
        "meta": b.meta,
    }
    if b.kind == "stand_in":
        doc["limit"] = STAND_IN_LIMIT
    else:
        doc["threshold"] = b.threshold
    if b.kind == "logistic":
        doc.update(
            mean=[float(v) for v in b.mean],
            std=[float(v) for v in b.std],
            coef=[float(v) for v in b.coef],
            intercept=b.intercept,
        )
    elif b.kind == "lightgbm":
        (path / MODEL_FILE).write_text(b.booster_text, encoding="utf-8")
    (path / BUNDLE_FILE).write_text(_canonical(doc), encoding="utf-8")


def load_bundle(path: Path) -> Bundle:
    """Read a bundle written by ``save_bundle``."""
    doc = json.loads((path / BUNDLE_FILE).read_text(encoding="utf-8"))
    if doc["format"] != FORMAT:
        raise ValueError(f"unknown C6 bundle format {doc['format']!r}")
    if doc["features"] != list(FEATURES):
        raise ValueError("the bundle was made for other features")
    b = Bundle(doc["kind"], doc["meta"])
    if b.kind != "stand_in":
        b.threshold = float(doc["threshold"])
    if b.kind == "logistic":
        b.mean, b.std = np.array(doc["mean"]), np.array(doc["std"])
        b.coef, b.intercept = np.array(doc["coef"]), float(doc["intercept"])
    elif b.kind == "lightgbm":
        b.booster_text = (path / MODEL_FILE).read_text(encoding="utf-8")
    return b


def bundle_sha256(path: Path) -> str:
    """Return one hash over every file of a bundle, in name order."""
    h = sha256()
    for f in sorted(p for p in path.iterdir() if p.is_file()):
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()
