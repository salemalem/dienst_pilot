"""How well does C4 recover the generator's latent preferences? Reads the ground truth.

Only eval/ may read the ground-truth folder (ASSUMPTIONS §14). The true liking of a cell is the
generator's ``shift_affinity``: the person's latent weekday x shift preference, plus their night
tolerance on night and on-call shifts, minus their weekend aversion on Saturday and Sunday.
The learned score of a cell is log(wish rate) minus log(avoid rate), from each model's posterior
at the end of 2024. The pooled baseline's score is therefore the department-level ranking of the
cells, the same for everybody; the others add what they learned about the person.
Weekday Bereitschaftsdienst is not offered by the generator, so those cells are left out.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from dienstpilot_ml.features.preference import N_CELLS, cell_label
from dienstpilot_ml.preference_learner.models import Bundle
from dienstpilot_ml.training.c4_data import AVOID_K, AVOID_N, WISH_K, WISH_N

DAYS = ("mo", "di", "mi", "do", "fr", "sa", "so")
VALID = [
    i for i in range(N_CELLS) if not (cell_label(i)[1] == "bereitschaft" and cell_label(i)[0] < 5)
]


def true_affinity(root: Path) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Return per person the true liking per cell, and the pure weekday x shift preference."""
    lat = pl.read_parquet(root / "_truth" / "staff_latent.parquet")
    full: dict[str, np.ndarray] = {}
    pure: dict[str, np.ndarray] = {}
    for row in lat.iter_rows(named=True):
        pref = np.zeros(N_CELLS)
        aff = np.zeros(N_CELLS)
        for i in range(N_CELLS):
            wd, shift = cell_label(i)
            v = float(row[f"pref_{DAYS[wd]}_{shift}"])
            pref[i] = v
            if shift in ("nacht", "bereitschaft"):
                v += float(row["night_tolerance"])
            if wd >= 5:
                v -= float(row["weekend_aversion"])
            aff[i] = v
        full[row["staff_id"]] = aff
        pure[row["staff_id"]] = pref
    return full, pure


def _ranks(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="mergesort")
    ranks = np.empty(len(v))
    ranks[order] = np.arange(len(v), dtype=float)
    for u in np.unique(v):  # average rank for ties
        m = v == u
        ranks[m] = ranks[m].mean()
    return ranks


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Return the Spearman rank correlation (NaN if either side is constant)."""
    ra, rb = _ranks(a), _ranks(b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def score(b: Bundle, c: np.ndarray) -> np.ndarray:
    """Return the learned score per cell from one person's counts (4 x cells)."""
    pw = b.predict("wish", c[WISH_K], c[WISH_N])
    pa = b.predict("avoid", c[AVOID_K], c[AVOID_N])
    return np.log(pw) - np.log(pa)


def _mean(values: list[float]) -> float | None:
    ok = [x for x in values if not np.isnan(x)]
    return float(np.mean(ok)) if ok else None


def recovery(
    root: Path,
    bundles: dict[str, Bundle],
    train: dict[str, np.ndarray],
    little_history: Callable[[str], bool],
) -> dict[str, Any]:
    """Return the mean per-person rank correlation of each model, overall and by history."""
    full, pure = true_affinity(root)
    zero = np.zeros((4, N_CELLS))
    out: dict[str, Any] = {
        "target": "generator shift_affinity per weekday x shift cell (module docstring)",
        "cells_used": len(VALID),
        "people": len(full),
        "models": {},
    }
    for kind, b in bundles.items():
        groups: dict[str, list[tuple[float, float]]] = {"all": [], "little_history": [], "rest": []}
        for staff, aff in full.items():
            s = score(b, train.get(staff, zero))
            rho = (spearman(s[VALID], aff[VALID]), spearman(s[VALID], pure[staff][VALID]))
            groups["all"].append(rho)
            groups["little_history" if little_history(staff) else "rest"].append(rho)
        out["models"][kind] = {
            g: {
                "people": len(v),
                "mean_spearman_vs_affinity": _mean([r[0] for r in v]),
                "mean_spearman_vs_pure_preference": _mean([r[1] for r in v]),
            }
            for g, v in groups.items()
        }
    return out
