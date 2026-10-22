"""Metrics for count forecasts."""

import numpy as np

from dienstpilot_ml.features.absence import Matrix


def poisson_deviance(y: Matrix, mu: Matrix) -> float:
    """Return the mean Poisson deviance (mu must be positive)."""
    ratio = np.where(y > 0, y / mu, 1.0)
    return float(np.mean(2.0 * (y * np.log(ratio) - (y - mu))))


def deviance_terms(y: Matrix, mu: Matrix) -> Matrix:
    """Return the Poisson deviance of every row."""
    ratio = np.where(y > 0, y / mu, 1.0)
    return np.asarray(2.0 * (y * np.log(ratio) - (y - mu)))


def mae(y: Matrix, mu: Matrix) -> float:
    """Return the mean absolute error of the expected count."""
    return float(np.mean(np.abs(y - mu)))


def coverage(y: Matrix, low: Matrix, high: Matrix) -> float:
    """Return the share of observations inside [low, high]."""
    return float(np.mean((y >= low) & (y <= high)))
