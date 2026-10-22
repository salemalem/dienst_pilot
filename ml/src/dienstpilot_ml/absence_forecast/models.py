"""C3 models as they are used for prediction: the same code in training, eval and the API.

Fitting lives in ``dienstpilot_ml.training`` (it needs statsmodels). Prediction needs only numpy
and LightGBM, so the API can load a bundle without the training stack.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

from dienstpilot_ml.features.absence import (
    FEATURE_NAMES,
    INDEX,
    FeatureBuilder,
    Matrix,
)

MU_FLOOR = 0.05
LEVEL = 0.8
SCALE_OFFSET = 0.5
BUCKETS = ((1, 7), (8, 21), (22, 42))
BUNDLE_FILES = ("bundle.json", "model.txt")
FORMAT = 1


def bucket_of(horizon: int) -> int:
    """Return the index of the horizon bucket of a horizon in days."""
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= horizon <= hi:
            return i
    raise ValueError(f"horizon {horizon} is outside 1 to 42")


def glm_design(x: Matrix) -> Matrix:
    """Return the GLM design matrix for raw feature rows (intercept, weekday, season, levels)."""
    dow = np.stack([(x[:, INDEX["dow"]] == d).astype(float) for d in range(1, 7)], axis=1)
    lvl28 = np.log1p(x[:, INDEX["level_28"]])
    lvl7 = np.log1p(x[:, INDEX["level_7"]])
    h = x[:, INDEX["horizon"]] / 42.0
    cols = [
        np.ones(len(x)),
        x[:, INDEX["doy_sin1"]],
        x[:, INDEX["doy_cos1"]],
        x[:, INDEX["doy_sin2"]],
        x[:, INDEX["doy_cos2"]],
        x[:, INDEX["is_holiday"]],
        x[:, INDEX["is_school_holiday"]],
        lvl28,
        lvl7,
        lvl28 * h,
    ]
    return np.column_stack([*cols[:1], dow, *cols[1:]])


class MeanModel(ABC):
    """Predicts the expected number of absent people for feature rows."""

    kind: str

    @abstractmethod
    def mean(
        self,
        x: Matrix,
        builder: FeatureBuilder,
        origins: Sequence[date],
        horizons: Sequence[int],
    ) -> Matrix:
        """Return one mean per row of ``x``; ``origins`` and ``horizons`` are per row."""

    @abstractmethod
    def params(self) -> dict[str, Any]:
        """Return the JSON-serialisable parameters of the model (not the LightGBM trees)."""


class SeasonalNaive(MeanModel):
    """Mean count around the same weekday of the last ``years`` years (centred window)."""

    kind = "seasonal_naive"

    def __init__(self, window: int, years: int) -> None:
        """Set the half-width of the window in days and how many years back to average."""
        self.window, self.years = window, years

    def mean(
        self,
        x: Matrix,
        builder: FeatureBuilder,
        origins: Sequence[date],
        horizons: Sequence[int],
    ) -> Matrix:
        """Return the seasonal-naive mean; falls back to the 91-day level without a last year."""
        out = np.array(
            [
                builder.seasonal(o, o + timedelta(days=h), self.window, self.years)
                for o, h in zip(origins, horizons, strict=True)
            ]
        )
        return np.where(np.isnan(out), x[:, INDEX["level_91"]], out)

    def params(self) -> dict[str, Any]:
        """Return window and years."""
        return {"window": self.window, "years": self.years}


class GlmModel(MeanModel):
    """Poisson or negative-binomial GLM with a log link; only the coefficients are stored."""

    def __init__(self, kind: str, coef: Sequence[float], alpha: float | None = None) -> None:
        """Keep the coefficients (and the NB dispersion, for the record)."""
        self.kind = kind
        self.coef = np.asarray(coef, dtype=np.float64)
        self.alpha = alpha

    def mean(
        self,
        x: Matrix,
        builder: FeatureBuilder,
        origins: Sequence[date],
        horizons: Sequence[int],
    ) -> Matrix:
        """Return exp(design @ coef)."""
        return np.asarray(np.exp(glm_design(x) @ self.coef))

    def params(self) -> dict[str, Any]:
        """Return the coefficients."""
        return {"coef": [float(c) for c in self.coef], "alpha": self.alpha}


class LightGbmModel(MeanModel):
    """LightGBM with a Poisson objective."""

    kind = "lightgbm"

    def __init__(self, booster: lgb.Booster, hyper: dict[str, Any]) -> None:
        """Keep the trained booster and the hyperparameters it was trained with."""
        self.booster = booster
        self.hyper = hyper

    def mean(
        self,
        x: Matrix,
        builder: FeatureBuilder,
        origins: Sequence[date],
        horizons: Sequence[int],
    ) -> Matrix:
        """Return the booster's predictions."""
        return np.asarray(self.booster.predict(x, num_threads=1))

    def params(self) -> dict[str, Any]:
        """Return the hyperparameters."""
        return {"hyper": self.hyper}


@dataclass(frozen=True)
class Bundle:
    """A servable C3 model: mean model plus split-conformal interval quantiles."""

    model: MeanModel
    quantiles: tuple[float, ...]  # one scaled-residual quantile per horizon bucket
    meta: dict[str, Any]

    def forecast(
        self, builder: FeatureBuilder, origin: date, horizons: Sequence[int]
    ) -> tuple[Matrix, Matrix, Matrix]:
        """Return (expected, low, high) for one origin and the given horizons."""
        x = builder.rows([origin] * len(horizons), horizons)
        rows = [origin] * len(horizons)
        mu = np.maximum(self.model.mean(x, builder, rows, horizons), MU_FLOOR)
        return (mu, *interval(mu, np.asarray(horizons), self.quantiles))


def interval(mu: Matrix, horizons: Matrix, quantiles: Sequence[float]) -> tuple[Matrix, Matrix]:
    """Return the conformal band mu +- q * sqrt(mu + 0.5), cut at zero."""
    q = np.array([quantiles[bucket_of(int(h))] for h in horizons])
    half = q * np.sqrt(mu + SCALE_OFFSET)
    return np.maximum(mu - half, 0.0), mu + half


def conformal_quantiles(
    y: Matrix, mu: Matrix, horizons: Matrix, level: float = LEVEL
) -> tuple[float, ...]:
    """Return the split-conformal quantile of the scaled absolute residual per horizon bucket."""
    score = np.abs(y - mu) / np.sqrt(mu + SCALE_OFFSET)
    out = []
    for lo, hi in BUCKETS:
        s = np.sort(score[(horizons >= lo) & (horizons <= hi)])
        n = len(s)
        k = min(n - 1, int(np.ceil((n + 1) * level)) - 1)
        out.append(float(s[k]))
    return tuple(out)


def _canonical(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def save_bundle(path: Path, bundle: Bundle) -> None:
    """Write bundle.json (and model.txt for LightGBM) into ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    doc = {
        "format": FORMAT,
        "kind": bundle.model.kind,
        "params": bundle.model.params(),
        "feature_names": list(
            __import__("dienstpilot_ml.features.absence", fromlist=["x"]).FEATURE_NAMES
        ),
        "buckets": [list(b) for b in BUCKETS],
        "conformal": {
            "level": LEVEL,
            "scale_offset": SCALE_OFFSET,
            "quantiles": list(bundle.quantiles),
        },
        "mu_floor": MU_FLOOR,
        "meta": bundle.meta,
    }
    (path / "bundle.json").write_text(_canonical(doc), encoding="utf-8")
    model_file = path / "model.txt"
    if isinstance(bundle.model, LightGbmModel):
        model_file.write_text(bundle.model.booster.model_to_string(), encoding="utf-8")
    elif model_file.exists():
        model_file.unlink()


def bundle_sha256(path: Path) -> str:
    """Return one hash over the bundle's files (names and bytes)."""
    h = sha256()
    for name in BUNDLE_FILES:
        f = path / name
        if f.exists():
            h.update(name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def load_bundle(path: Path) -> Bundle:
    """Load a bundle written by ``save_bundle``."""
    doc = json.loads((path / "bundle.json").read_text(encoding="utf-8"))
    if doc["format"] != FORMAT or doc["feature_names"] != list(FEATURE_NAMES):
        raise ValueError("the bundle does not match this version of the features")
    kind, params = doc["kind"], doc["params"]
    model: MeanModel
    if kind == "seasonal_naive":
        model = SeasonalNaive(params["window"], params["years"])
    elif kind in ("poisson_glm", "nb_glm"):
        model = GlmModel(kind, params["coef"], params["alpha"])
    elif kind == "lightgbm":
        booster = lgb.Booster(model_str=(path / "model.txt").read_text(encoding="utf-8"))
        model = LightGbmModel(booster, params["hyper"])
    else:
        raise ValueError(f"unknown model kind {kind!r}")
    return Bundle(model, tuple(doc["conformal"]["quantiles"]), doc["meta"])
