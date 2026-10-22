"""C5 models: base rate, logistic regression, and LightGBM with isotonic calibration.

A bundle holds model parameters only (a rate, coefficients, trees and calibration steps) and the
feature definitions. Never a person-level value or a staff identifier. Serving needs numpy and
lightgbm; training adds scipy.
"""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from dienstpilot_ml.features.cover import FEATURES, NUMERIC, SHIFT_TYPES, Matrix

FORMAT = "c5-bundle-1"
KINDS = ("base_rate", "logistic", "lightgbm")
BUNDLE_FILE = "bundle.json"
MODEL_FILE = "model.txt"
P_MIN, P_MAX = 0.01, 0.99
Vector = NDArray[np.float64]


@dataclass
class Isotonic:
    """A non-decreasing function fitted by pool-adjacent-violators, applied by interpolation."""

    x: Vector
    y: Vector

    def __call__(self, p: Vector) -> Vector:
        """Return calibrated probabilities."""
        return np.clip(np.interp(p, self.x, self.y), P_MIN, P_MAX)


def fit_isotonic(p: Vector, y: Vector) -> Isotonic:
    """Fit isotonic regression of the outcomes y on the predictions p."""
    order = np.argsort(p, kind="stable")
    ps, ys = p[order], y[order]
    # Blocks of (sum of y, weight, mean of p); merge neighbours while the means decrease.
    blocks: list[list[float]] = []
    for pi, yi in zip(ps, ys, strict=True):
        blocks.append([float(yi), 1.0, float(pi), float(pi)])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] >= blocks[-1][0] / blocks[-1][1]:
            b = blocks.pop()
            a = blocks[-1]
            a[0] += b[0]
            a[1] += b[1]
            a[3] = b[3]
    xs: list[float] = []
    vals: list[float] = []
    for s, w, lo, hi in blocks:
        for x in (lo, hi):
            if not xs or x > xs[-1]:
                xs.append(x)
                vals.append(s / w)
            else:
                vals[-1] = s / w
    return Isotonic(np.array(xs), np.clip(np.array(vals), P_MIN, P_MAX))


def design(x: Matrix, mean: Vector, std: Vector) -> Matrix:
    """Return the logistic design matrix: standardised numeric columns and one-hot shift type."""
    num = x[:, 1:]
    z = (num - mean) / std
    onehot = np.zeros((len(x), len(SHIFT_TYPES)))
    onehot[np.arange(len(x)), x[:, 0].astype(int)] = 1.0
    return np.hstack([z, onehot])


@dataclass
class Bundle:
    """One C5 model with everything needed to predict."""

    kind: str
    meta: dict[str, Any]
    rate: float = 0.0  # base_rate
    mean: Vector = field(default_factory=lambda: np.zeros(len(NUMERIC)))  # logistic
    std: Vector = field(default_factory=lambda: np.ones(len(NUMERIC)))
    coef: Vector = field(default_factory=lambda: np.zeros(len(NUMERIC) + len(SHIFT_TYPES)))
    intercept: float = 0.0
    booster_text: str = ""  # lightgbm
    calibrator: Isotonic | None = None
    _booster: Any = None

    def predict(self, x: Matrix) -> Vector:
        """Return P(accept) for each row of ``x`` (columns in ``FEATURES`` order)."""
        if self.kind == "base_rate":
            return np.full(len(x), self.rate)
        if self.kind == "logistic":
            z = design(x, self.mean, self.std) @ self.coef + self.intercept
            return np.clip(1.0 / (1.0 + np.exp(-z)), P_MIN, P_MAX)
        if self._booster is None:
            import lightgbm as lgb

            self._booster = lgb.Booster(model_str=self.booster_text)
        raw = np.asarray(self._booster.predict(x), dtype=np.float64)
        assert self.calibrator is not None
        return self.calibrator(raw)


def _canonical(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def save_bundle(path: Path, b: Bundle) -> None:
    """Write bundle.json (and model.txt for LightGBM) into ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "format": FORMAT,
        "kind": b.kind,
        "features": list(FEATURES),
        "shift_types": list(SHIFT_TYPES),
        "meta": b.meta,
    }
    if b.kind == "base_rate":
        doc["rate"] = b.rate
    elif b.kind == "logistic":
        doc.update(
            mean=[float(v) for v in b.mean],
            std=[float(v) for v in b.std],
            coef=[float(v) for v in b.coef],
            intercept=b.intercept,
        )
    else:
        assert b.calibrator is not None
        doc["calibrator"] = {
            "x": [float(v) for v in b.calibrator.x],
            "y": [float(v) for v in b.calibrator.y],
        }
        (path / MODEL_FILE).write_text(b.booster_text, encoding="utf-8")
    (path / BUNDLE_FILE).write_text(_canonical(doc), encoding="utf-8")


def load_bundle(path: Path) -> Bundle:
    """Read a bundle written by ``save_bundle``."""
    doc = json.loads((path / BUNDLE_FILE).read_text(encoding="utf-8"))
    if doc["format"] != FORMAT:
        raise ValueError(f"unknown C5 bundle format {doc['format']!r}")
    if doc["features"] != list(FEATURES):
        raise ValueError("the bundle was made for other features")
    b = Bundle(doc["kind"], doc["meta"])
    if b.kind == "base_rate":
        b.rate = float(doc["rate"])
    elif b.kind == "logistic":
        b.mean, b.std = np.array(doc["mean"]), np.array(doc["std"])
        b.coef, b.intercept = np.array(doc["coef"]), float(doc["intercept"])
    else:
        b.booster_text = (path / MODEL_FILE).read_text(encoding="utf-8")
        b.calibrator = Isotonic(np.array(doc["calibrator"]["x"]), np.array(doc["calibrator"]["y"]))
    return b


def bundle_sha256(path: Path) -> str:
    """Return one hash over every file of a bundle, in name order."""
    h = sha256()
    for f in sorted(p for p in path.iterdir() if p.is_file()):
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()
