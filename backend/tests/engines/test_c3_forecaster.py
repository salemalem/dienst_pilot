"""The C3 adapter: horizons, the demo clock as the only 'now', department-level inputs."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from dienstpilot.engines.c3 import BUNDLE_DIR, RESULT, C3Forecaster
from dienstpilot.shared.ports import ForecastContext
from dienstpilot_ml.absence_forecast.models import bundle_sha256

HISTORY = [
    (date(2025, 1, 5) + timedelta(days=9 * i), date(2025, 1, 7) + timedelta(days=9 * i))
    for i in range(60)
]


def _ctx(as_of: date) -> ForecastContext:
    return ForecastContext(as_of, {}, frozenset(), frozenset())


def test_the_committed_bundle_is_the_one_the_eval_result_describes() -> None:
    doc = json.loads(RESULT.read_text(encoding="utf-8"))
    assert bundle_sha256(BUNDLE_DIR) == doc["champion"]["bundle_sha256"]
    assert C3Forecaster().info.implementation == "built"


def test_forecast_follows_the_as_of_date_and_stays_in_one_to_42_days() -> None:
    f = C3Forecaster()
    as_of = date(2026, 10, 20)
    days = [as_of + timedelta(days=i) for i in range(14)]
    out = f.forecast(days, HISTORY, _ctx(as_of))
    assert [x.day for x in out] == days
    assert all(0 <= x.low <= x.expected <= x.high for x in out)
    with pytest.raises(ValueError):
        f.forecast([as_of - timedelta(days=1)], HISTORY, _ctx(as_of))  # the past
    with pytest.raises(ValueError):
        f.forecast([as_of + timedelta(days=43)], HISTORY, _ctx(as_of))  # beyond 42 days ahead


def test_same_inputs_give_the_same_forecast() -> None:
    f = C3Forecaster()
    d = [date(2026, 10, 21)]
    assert f.forecast(d, HISTORY, _ctx(date(2026, 10, 20))) == f.forecast(
        d, HISTORY, _ctx(date(2026, 10, 20))
    )


def test_a_missing_bundle_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        C3Forecaster(tmp_path)
