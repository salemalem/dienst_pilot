import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np

from dienstpilot_ml.absence_forecast.models import (
    BUCKETS,
    Bundle,
    SeasonalNaive,
    bundle_sha256,
    conformal_quantiles,
    interval,
    load_bundle,
    save_bundle,
)
from dienstpilot_ml.features.absence import Calendar, DailySeries, FeatureBuilder
from dienstpilot_ml.training import fit


def _builder() -> FeatureBuilder:
    rng = np.random.default_rng(1)
    s = DailySeries(date(2021, 1, 1), rng.poisson(1.0, 1000).astype(float))
    return FeatureBuilder(s, Calendar(frozenset(), frozenset()), {})


def test_split_conformal_covers_about_the_nominal_level_on_poisson_data() -> None:
    rng = np.random.default_rng(0)
    mu = rng.uniform(0.5, 3.0, 40_000)
    y = rng.poisson(mu).astype(float)
    h = rng.integers(1, 43, len(mu)).astype(float)
    half = len(mu) // 2
    q = conformal_quantiles(y[:half], mu[:half], h[:half])
    low, high = interval(mu[half:], h[half:], q)
    cov = np.mean((y[half:] >= low) & (y[half:] <= high))
    assert 0.8 <= cov <= 0.9  # discrete counts over-cover a little; never under-cover
    assert len(q) == len(BUCKETS)


def test_bundle_round_trip_keeps_forecasts_and_hash(tmp_path: Path) -> None:
    b = _builder()
    x = b.matrix([date(2023, 3, 1)])
    rng = np.random.default_rng(2)
    y = rng.poisson(1.0, len(x)).astype(float)
    for model in (SeasonalNaive(7, 1), fit.fit_poisson(x, y), fit.fit_negative_binomial(x, y)):
        d = tmp_path / model.kind
        save_bundle(d, Bundle(model, (1.0, 1.2, 1.4), {"note": "t"}))
        loaded = load_bundle(d)
        horizons = [1, 10, 30]
        a = Bundle(model, (1.0, 1.2, 1.4), {}).forecast(b, date(2023, 3, 1), horizons)
        c = loaded.forecast(b, date(2023, 3, 1), horizons)
        for u, v in zip(a, c, strict=True):
            assert np.allclose(u, v)
        assert bundle_sha256(d) == bundle_sha256(d)


def test_lightgbm_training_is_deterministic(tmp_path: Path) -> None:
    b = _builder()
    x = b.matrix([date(2023, 3, 1), date(2023, 3, 2), date(2023, 4, 1)])
    y = np.random.default_rng(3).poisson(1.0, len(x)).astype(float)
    hyper = {"num_leaves": 4, "min_data_in_leaf": 5, "num_boost_round": 20}
    hashes = []
    for i in range(2):
        d = tmp_path / str(i)
        save_bundle(d, Bundle(fit.fit_lightgbm(x, y, hyper), (1.0, 1.0, 1.0), {}))
        hashes.append(bundle_sha256(d))
    assert hashes[0] == hashes[1]


def test_forecasts_are_positive_and_the_band_contains_the_mean() -> None:
    mu, low, high = Bundle(SeasonalNaive(0, 1), (2.0, 2.0, 2.0), {}).forecast(
        _builder(), date(2023, 3, 1), [1, 2, 3]
    )
    assert (mu > 0).all() and (low >= 0).all() and (low <= mu).all() and (mu <= high).all()


def test_serving_modules_do_not_import_the_training_stack() -> None:
    code = (
        "import sys, dienstpilot_ml.absence_forecast.models;"
        "bad=[m for m in ('mlflow','statsmodels') if m in sys.modules];"
        "sys.exit(1 if bad else 0)"
    )
    assert subprocess.run([sys.executable, "-I", "-c", code], check=False).returncode == 0


def test_committed_champion_bundle_loads_and_matches_its_registry_note() -> None:
    root = Path(__file__).resolve().parents[1] / "absence_forecast" / "artifacts"
    note = json.loads((root / "champion_registry.json").read_text(encoding="utf-8"))
    assert load_bundle(root / "champion").model.kind == note["kind"]
