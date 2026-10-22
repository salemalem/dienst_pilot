from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from dienstpilot_ml.cover_ranker.models import fit_isotonic
from dienstpilot_ml.cover_ranker.policy import BUCKET_WIDTH, Ranked, bucket, order
from dienstpilot_ml.features.cover import (
    FEATURES,
    confirmed_pref,
    days_since,
    month_contract_hours,
    notice_hours,
)
from dienstpilot_ml.training.c5 import (
    GRID,
    auc,
    brier,
    ece,
    fit_base_rate,
    fit_lightgbm_raw,
    fit_logistic,
)

DATA = Path(__file__).resolve().parents[2] / "data/synthetic/v1"


def test_the_features_hold_no_protected_attribute_and_no_person_identifier() -> None:
    banned = ("age", "gender", "nationality", "family", "absence", "sick", "staff", "id")
    assert not [f for f in FEATURES if any(b in f.split("_") for b in banned)]


def test_feature_definitions() -> None:
    assert month_contract_hours(40.0, date(2025, 3, 1)) == 8.0 * 21
    t = datetime(2025, 3, 3, 6, 40)
    assert notice_hours(t, datetime(2025, 3, 3, 7, 30)) == pytest.approx(50 / 60)
    assert notice_hours(t, datetime(2025, 3, 9, 7, 30)) == 72.0  # limited
    assert notice_hours(t, datetime(2025, 3, 3, 6, 0)) == 0.0
    assert days_since(None, t) == 365.0
    assert days_since(datetime(2025, 3, 1, 6, 40), t) == pytest.approx(2.0)


def test_only_the_persons_own_confirmed_preferences_count_and_only_before_the_request() -> None:
    wishes = [(date(2025, 2, 1), "nacht"), (date(2025, 2, 2), "nacht"), (date(2025, 2, 3), "frueh")]
    avoids = [(date(2025, 2, 5), "nacht"), (date(2024, 1, 1), "nacht")]  # the latter is too old
    assert confirmed_pref(wishes, avoids, date(2025, 3, 1), "nacht") == 1.0
    assert confirmed_pref(wishes, avoids, date(2025, 1, 1), "nacht") == 0.0  # not yet confirmed
    assert (
        confirmed_pref(
            [(date(2025, 2, d), "nacht") for d in range(1, 9)], [], date(2025, 3, 1), "nacht"
        )
        == 5.0
    )


def test_isotonic_is_monotone_and_keeps_the_mean() -> None:
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 400)
    y = (rng.uniform(0, 1, 400) < p).astype(float)
    iso = fit_isotonic(p, y)
    grid = np.linspace(0, 1, 200)
    out = iso(grid)
    assert np.all(np.diff(out) >= -1e-12)
    assert out.min() >= 0.01 and out.max() <= 0.99
    assert abs(iso(p).mean() - y.mean()) < 0.03


def test_metrics_on_known_cases() -> None:
    y = np.array([1.0, 0.0, 1.0, 0.0])
    assert auc(y, np.array([0.9, 0.1, 0.8, 0.2])) == 1.0
    assert auc(y, np.full(4, 0.5)) == 0.5
    assert brier(y, np.array([1.0, 0.0, 1.0, 0.0])) == 0.0
    assert ece(y, y.copy()) == 0.0


def _toy(n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(2)
    x = np.column_stack(
        [
            rng.integers(0, 5, n),
            rng.uniform(0.3, 1.1, n),
            rng.uniform(0, 365, n),
            rng.integers(0, 5, n),
            rng.uniform(0, 72, n),
            rng.integers(0, 7, n),
            rng.uniform(4, 8, n),
            rng.integers(-2, 6, n),
        ]
    ).astype(float)
    y = (rng.uniform(0, 1, n) < 0.3 + 0.4 * (x[:, 2] > 200)).astype(float)
    return x, y


def test_fitting_is_deterministic() -> None:
    x, y = _toy()
    assert fit_lightgbm_raw(x, y, GRID[0]) == fit_lightgbm_raw(x, y, GRID[0])
    a, b = fit_logistic(x, y, {}), fit_logistic(x, y, {})
    assert np.array_equal(a.coef, b.coef) and a.intercept == b.intercept
    assert fit_base_rate(y, {}).rate == fit_base_rate(y, {}).rate


@given(
    st.lists(
        st.tuples(st.integers(0, 12), st.floats(0.0, 1.0), st.floats(0.0, 1.2)),
        min_size=1,
        max_size=15,
    )
)
def test_a_probability_never_moves_a_person_across_a_burden_bucket(
    rows: list[tuple[int, float, float]],
) -> None:
    cands = [Ranked(f"s{i}", c, h, p) for i, (c, p, h) in enumerate(rows)]
    result = order(cands)
    assert sorted(c.staff_id for c in result) == sorted(c.staff_id for c in cands)
    buckets = [bucket(c.covers_last_90_days) for c in result]
    assert buckets == sorted(buckets)  # least burdened bucket first, whatever the probabilities
    for b in set(buckets):  # inside a bucket: probability high to low
        inside = [round(c.p_accept, 4) for c in result if bucket(c.covers_last_90_days) == b]
        assert inside == sorted(inside, reverse=True)


def test_buckets_are_two_covers_wide_and_ties_fall_back_to_hours_then_id() -> None:
    assert BUCKET_WIDTH == 2
    assert [bucket(c) for c in range(6)] == [0, 0, 1, 1, 2, 2]
    cands = [Ranked("b", 1, 0.9, 0.5), Ranked("a", 0, 0.7, 0.5), Ranked("c", 3, 0.1, 0.99)]
    assert [c.staff_id for c in order(cands)] == ["a", "b", "c"]
    assert [c.staff_id for c in order(cands, width=1)] == ["a", "b", "c"]
    same = [Ranked("z", 0, 0.5, 0.4), Ranked("y", 1, 0.5, 0.4)]
    assert [c.staff_id for c in order(same)] == ["y", "z"]  # same bucket, same P, same hours: id


@pytest.mark.skipif(not DATA.exists(), reason="needs the generated dataset")
def test_training_data_never_contains_2025_offers() -> None:
    from dienstpilot_ml.training.c5 import TRAIN_END
    from dienstpilot_ml.training.c5_data import load

    t = load(DATA, through=TRAIN_END)
    assert t.year.max() == 2024
    assert t.x.shape[1] == len(FEATURES)
