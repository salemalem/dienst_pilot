from datetime import date, timedelta

import numpy as np

from dienstpilot_ml.features.absence import (
    FEATURE_NAMES,
    MIN_ORIGIN,
    Calendar,
    DailySeries,
    FeatureBuilder,
    daily_counts,
)

START = date(2021, 1, 1)
CAL = Calendar(frozenset({date(2023, 5, 1)}), frozenset({date(2023, 7, 10)}))


def _series(seed: int = 0, days: int = 1200) -> DailySeries:
    rng = np.random.default_rng(seed)
    return DailySeries(START, rng.poisson(1.2, days).astype(float))


def test_daily_counts_clips_intervals_at_the_end_of_the_observed_period() -> None:
    s = daily_counts([(date(2021, 1, 3), date(2021, 1, 9))], START, date(2021, 1, 5))
    assert s.values.tolist() == [0, 0, 1, 1, 1]
    assert s.end == date(2021, 1, 5)


def test_features_of_an_origin_do_not_change_when_later_data_changes() -> None:
    origin = date(2023, 6, 1)
    a = _series()
    k = (origin - START).days
    changed = a.values.copy()
    changed[k + 1 :] += 7.0  # everything after the origin differs
    nights = {origin - timedelta(days=i): 3 for i in range(10)}
    rows_a = FeatureBuilder(a, CAL, nights).matrix([origin])
    rows_b = FeatureBuilder(DailySeries(START, changed), CAL, nights).matrix([origin])
    assert np.array_equal(rows_a, rows_b, equal_nan=True)


def test_features_do_not_depend_on_nights_after_the_origin() -> None:
    origin = date(2023, 6, 1)
    s = _series()
    base = {origin - timedelta(days=i): 2 for i in range(7)}
    later = {**base, origin + timedelta(days=1): 99}
    assert np.array_equal(
        FeatureBuilder(s, CAL, base).matrix([origin]),
        FeatureBuilder(s, CAL, later).matrix([origin]),
    )


def test_calendar_flags_refer_to_the_target_day() -> None:
    s = _series()
    b = FeatureBuilder(s, CAL, {})
    row = b.row(date(2023, 4, 30), 1)  # target 1 May
    idx = {n: i for i, n in enumerate(FEATURE_NAMES)}
    assert row[idx["is_holiday"]] == 1.0 and row[idx["is_school_holiday"]] == 0.0
    assert row[idx["dow"]] == date(2023, 5, 1).weekday()


def test_last_year_features_are_missing_without_a_full_year_of_history() -> None:
    s = _series()
    b = FeatureBuilder(s, CAL, {})
    row = b.row(MIN_ORIGIN, 10)
    assert np.isnan(row[FEATURE_NAMES.index("last_year_7d")])
    later = b.row(date(2022, 6, 1), 10)
    assert not np.isnan(later[FEATURE_NAMES.index("last_year_7d")])


def test_the_builder_takes_only_department_aggregates() -> None:
    # Inputs are a daily series, a calendar and nights per day: no staff identifier can enter.
    import inspect

    params = inspect.signature(FeatureBuilder.__init__).parameters
    assert set(params) == {"self", "series", "calendar", "night_shifts"}
    assert not any("staff" in n or "person" in n for n in FEATURE_NAMES)
