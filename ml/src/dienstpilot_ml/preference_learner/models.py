"""C4 as it is used for prediction: the same code in training, eval and the API.

Two Bernoulli processes per person and cell (see ``ml/preference_learner/PROMOTION_RULE.md``): the
wish process and the avoid process. A bundle holds department-level quantities only: the pooled
rate of every cell and one concentration per process. Never a person-level value or identifier.
"""

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np

from dienstpilot_ml.features.preference import N_CELLS, SHIFTS, Counts, cell_label

FORMAT = "c4-bundle-1"
P_MIN, P_MAX = 0.001, 0.999
KINDS = ("pooled", "raw", "hierarchical")
BUNDLE_FILE = "bundle.json"
DRAWS = 4000
DRAW_SEED = 20261020
MIN_EVENTS = 2
MIN_RATIO = 2.0
MIN_PROBABILITY = 0.8
MAX_SUGGESTIONS = 3


@dataclass(frozen=True)
class Bundle:
    """One C4 model: its kind, the pooled cell rates and the concentrations."""

    kind: str
    m_wish: Counts
    m_avoid: Counts
    kappa_wish: float
    kappa_avoid: float
    meta: dict[str, Any]

    def prior(self, process: str) -> tuple[Counts, float]:
        """Return the pooled rates and concentration of ``process`` ("wish" or "avoid")."""
        if process == "wish":
            return self.m_wish, self.kappa_wish
        return self.m_avoid, self.kappa_avoid

    def predict(self, process: str, k: Counts, n: Counts) -> Counts:
        """Return the model's probability per cell given the person's events k of n trials."""
        m, kappa = self.prior(process)
        m = np.clip(m, P_MIN, P_MAX)
        if self.kind == "pooled":
            p = m.copy()
        elif self.kind == "raw":
            p = np.where(n > 0, k / np.maximum(n, 1.0), m)
        else:
            p = (k + kappa * m) / (n + kappa)
        return np.clip(p, P_MIN, P_MAX)


@dataclass(frozen=True)
class Suggestion:
    """A suggested preference with the numbers behind it."""

    kind: str  # "prefer" | "avoid"
    weekday: int
    shift_type: str
    events: int
    trials: int
    rate: float  # the model's probability for this person and cell
    department_rate: float
    probability: float  # P(person's rate > department rate)


def _posterior(b: Bundle, process: str, k: Counts, n: Counts) -> tuple[Counts, Counts]:
    """Return Beta parameters of the person's rate per cell (flat prior for the raw baseline)."""
    m, kappa = b.prior(process)
    m = np.clip(m, P_MIN, P_MAX)
    if b.kind == "raw":
        return k + 1.0, n - k + 1.0
    return k + kappa * m, n - k + kappa * (1.0 - m)


def suggest(
    b: Bundle, wish_k: Counts, wish_n: Counts, avoid_k: Counts, avoid_n: Counts
) -> list[Suggestion]:
    """Apply the display policy of the promotion rule to one person's counts.

    The pooled baseline has no personal signal, so it never suggests. For the raw baseline the
    probability uses the flat Beta(k + 1, n - k + 1) posterior (an implementation choice the rule
    leaves open).
    """
    if b.kind == "pooled":
        return []
    rng = np.random.default_rng(DRAW_SEED)
    out: list[Suggestion] = []
    for kind, process, k, n in (
        ("prefer", "wish", wish_k, wish_n),
        ("avoid", "avoid", avoid_k, avoid_n),
    ):
        m = np.clip(b.prior(process)[0], P_MIN, P_MAX)
        p = b.predict(process, k, n)
        a, bb = _posterior(b, process, k, n)
        for i in range(N_CELLS):
            if k[i] < MIN_EVENTS or p[i] < MIN_RATIO * m[i]:
                continue
            prob = float(np.mean(rng.beta(a[i], bb[i], DRAWS) > m[i]))
            if prob < MIN_PROBABILITY:
                continue
            wd, shift = cell_label(i)
            out.append(
                Suggestion(kind, wd, shift, int(k[i]), int(n[i]), float(p[i]), float(m[i]), prob)
            )
    out.sort(key=lambda s: (-s.probability, s.kind, s.weekday, s.shift_type))
    return out[:MAX_SUGGESTIONS]


def _canonical(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def save_bundle(path: Path, b: Bundle) -> None:
    """Write bundle.json into ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    doc = {
        "format": FORMAT,
        "kind": b.kind,
        "shifts": list(SHIFTS),
        "cells": "index = weekday * 4 + shift index, weekday 0 = Monday",
        "m_wish": [float(x) for x in b.m_wish],
        "m_avoid": [float(x) for x in b.m_avoid],
        "kappa_wish": b.kappa_wish,
        "kappa_avoid": b.kappa_avoid,
        "p_clip": [P_MIN, P_MAX],
        "meta": b.meta,
    }
    (path / BUNDLE_FILE).write_text(_canonical(doc), encoding="utf-8")


def load_bundle(path: Path) -> Bundle:
    """Read a bundle written by ``save_bundle``."""
    doc = json.loads((path / BUNDLE_FILE).read_text(encoding="utf-8"))
    if doc["format"] != FORMAT:
        raise ValueError(f"unknown C4 bundle format {doc['format']!r}")
    return Bundle(
        doc["kind"],
        np.array(doc["m_wish"]),
        np.array(doc["m_avoid"]),
        float(doc["kappa_wish"]),
        float(doc["kappa_avoid"]),
        dict(doc["meta"]),
    )


def bundle_sha256(path: Path) -> str:
    """Return the hash of the bundle file."""
    return sha256(
        BUNDLE_FILE.encode() + b"\0" + (path / BUNDLE_FILE).read_bytes() + b"\0"
    ).hexdigest()
