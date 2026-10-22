"""Fitting C3 models. Deterministic: fixed seed, one thread, LightGBM deterministic mode."""

import warnings
from itertools import product
from typing import Any

import lightgbm as lgb
import numpy as np
import statsmodels.api as sm

from dienstpilot_ml.absence_forecast.models import (
    GlmModel,
    LightGbmModel,
    SeasonalNaive,
    glm_design,
)
from dienstpilot_ml.features.absence import FEATURE_NAMES, Matrix

SEED = 20261020

SEASONAL_GRID = tuple(product((0, 3, 7, 14), (1, 2)))  # (half-width in days, years back)
LGBM_GRID = tuple(
    {"num_leaves": nl, "min_data_in_leaf": md, "num_boost_round": nr}
    for nl, md, nr in product((4, 8), (200, 800), (150, 400))
)
LGBM_FIXED: dict[str, Any] = {
    "objective": "poisson",
    "learning_rate": 0.03,
    "feature_fraction": 1.0,
    "bagging_fraction": 1.0,
    "lambda_l2": 1.0,
    "seed": SEED,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 1,
    "verbose": -1,
}


def fit_poisson(x: Matrix, y: Matrix) -> GlmModel:
    """Fit the Poisson GLM."""
    res = sm.GLM(y, glm_design(x), family=sm.families.Poisson()).fit()
    return GlmModel("poisson_glm", res.params.tolist())


def fit_negative_binomial(x: Matrix, y: Matrix) -> GlmModel:
    """Fit the negative-binomial GLM (dispersion: moment estimate from the Poisson fit)."""
    design = glm_design(x)
    pois = sm.GLM(y, design, family=sm.families.Poisson()).fit()
    mu = pois.mu
    alpha = max(float(np.sum((y - mu) ** 2 - mu) / np.sum(mu**2)), 1e-6)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = sm.GLM(y, design, family=sm.families.NegativeBinomial(alpha=alpha)).fit()
    return GlmModel("nb_glm", res.params.tolist(), alpha)


def fit_lightgbm(x: Matrix, y: Matrix, hyper: dict[str, Any]) -> LightGbmModel:
    """Fit LightGBM with a Poisson objective."""
    params = {**LGBM_FIXED, **{k: v for k, v in hyper.items() if k != "num_boost_round"}}
    data = lgb.Dataset(x, label=y, feature_name=list(FEATURE_NAMES), free_raw_data=False)
    booster = lgb.train(params, data, num_boost_round=hyper["num_boost_round"])
    return LightGbmModel(booster, dict(hyper))


def seasonal(window: int, years: int) -> SeasonalNaive:
    """Return a seasonal-naive model (nothing to fit)."""
    return SeasonalNaive(window, years)
