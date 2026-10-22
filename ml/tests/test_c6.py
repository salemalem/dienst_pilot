"""C6: facts, features, the operating point and the models, on toy data."""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from dienstpilot_ml.features.leave import (
    FEATURES,
    NUMERIC,
    ROLES,
    LeaveFacts,
    build_facts,
    features,
    matrix,
)
from dienstpilot_ml.leave_surrogate.models import APPROVED_MAX, Bundle, load_bundle, save_bundle
from dienstpilot_ml.training.c6 import (
    GRID,
    auc,
    fit_lightgbm_text,
    fit_logistic,
    operating_point,
    precision_recall,
)


@dataclass(frozen=True)
class Doc:
    """A toy physician."""

    role: str
    quals: tuple[str, ...] = ()

    def available(self, d: date) -> bool:
        return True

    def contract(self, d: date) -> tuple[str, float] | None:
        return self.role, 40.0

    def holds(self, q: str, d: date) -> bool:
        return q in self.quals


START = date(2027, 7, 12)  # a Monday
END = date(2027, 7, 16)


def _facts(approved: dict[str, set[date]], pending: dict[str, set[date]]) -> LeaveFacts:
    doctors = {
        "me": Doc("assistenzarzt", ("nachtdienstfaehig",)),
        **{f"a{i}": Doc("assistenzarzt", ("nachtdienstfaehig",)) for i in range(6)},
        "f": Doc("facharzt", ("facharzt", "nachtdienstfaehig")),
        "c": Doc("chefaerztin", ("oberarzt",)),
    }
    demand = {
        START + timedelta(days=i): [
            ("frueh", "any", 2),
            ("nacht", "any", 1),
            ("nacht", "nachtdienstfaehig", 1),
        ]
        for i in range(5)
    }
    return build_facts(
        start=START,
        end=END,
        notice_days=90,
        requester="me",
        doctors=doctors,
        approved=approved,
        pending=pending,
        demand=demand,
        holidays={START + timedelta(days=2)},
        school_days={START, END},
    )


def _all() -> set[date]:
    return {START + timedelta(days=i) for i in range(5)}


def test_the_requester_counts_as_absent_and_the_chefaerztin_is_not_in_the_pool() -> None:
    f = _facts({}, {})
    # pool: 6 assistants + 1 specialist (not the requester, not the Chefärztin); heads: 2 + 1.
    assert [d.slack for d in f.days] == [7 - 3] * 5
    assert f.role == "assistenzarzt" and f.quals == ("nachtdienstfaehig",)
    assert f.overlapping == 0
    assert [d.holiday for d in f.days] == [False, False, True, False, False]
    assert [d.school for d in f.days] == [True, False, False, False, True]


def test_approved_and_pending_leave_reduce_the_slack_and_count_distinct_colleagues() -> None:
    f = _facts({"a0": _all(), "a1": {START}}, {"a2": _all(), "me": _all()})
    assert f.days[0].slack == 7 - 3 - 3  # a0, a1, a2 away on the first day
    assert f.days[1].slack == 7 - 3 - 2
    assert (f.days[0].approved, f.days[0].pending) == (2, 1)
    assert f.overlapping == 3  # the requester's own leave is not counted


def test_facts_round_trip_through_json_and_features_are_pure() -> None:
    f = _facts({"a0": _all()}, {"a2": {START}})
    g = LeaveFacts.from_json(f.to_json())
    assert g == f
    assert features(f) == features(g)
    m = matrix([features(f)])
    assert m.shape == (1, len(FEATURES)) and ("role", *NUMERIC) == FEATURES
    assert m[0, 0] == ROLES.index("assistenzarzt")
    assert m[0, APPROVED_MAX] == 1.0


def test_operating_point_maximises_precision_subject_to_recall() -> None:
    y = np.array([1, 1, 1, 0, 1, 0, 0, 0], dtype=float)
    score = np.array([0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.3, 0.1])
    # recall >= 0.75 needs three of the four positives: threshold 0.8 gives precision 1.0.
    assert operating_point(y, score, 0.75) == 0.8
    # recall 1.0 needs the fifth score (0.6): precision 4/5.
    assert operating_point(y, score, 1.0) == 0.6
    p, r = precision_recall(y, score >= 0.6)
    assert (p, r) == (0.8, 1.0)


def test_operating_point_ties_go_to_the_lower_threshold() -> None:
    y = np.array([1, 1, 1, 1], dtype=float)
    score = np.array([0.9, 0.8, 0.7, 0.6])
    assert operating_point(y, score, 0.5) == 0.6  # precision 1.0 everywhere: the lowest cut


def test_auc_of_a_perfect_and_a_useless_ranking() -> None:
    y = np.array([0, 0, 1, 1], dtype=float)
    assert auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5


def test_the_stand_in_bundle_is_the_old_rule() -> None:
    b = Bundle("stand_in", {})
    x = np.zeros((4, len(FEATURES)))
    x[:, APPROVED_MAX] = [0, 4, 5, 6]
    assert b.hint(x) == ["coverable", "coverable", "tight", "not_coverable"]
    assert list(b.yes(x)) == [True, True, False, False]


def _toy(n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    x = np.zeros((n, len(FEATURES)))
    x[:, 0] = rng.integers(0, len(ROLES), n)
    x[:, 1:] = rng.normal(size=(n, len(FEATURES) - 1))
    y = (x[:, 1] + 0.3 * rng.normal(size=n) > 0).astype(float)
    return x, y


def test_training_is_deterministic_and_the_bundle_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    x, y = _toy()
    a = fit_lightgbm_text(x, y, GRID[0])
    assert a == fit_lightgbm_text(x, y, GRID[0])
    lin1, lin2 = fit_logistic(x, y, {}), fit_logistic(x, y, {})
    assert np.array_equal(lin1.coef, lin2.coef)
    for b in (Bundle("lightgbm", {"m": "x"}, threshold=0.4, booster_text=a), lin1):
        b.threshold = 0.4
        save_bundle(tmp_path / b.kind, b)
        c = load_bundle(tmp_path / b.kind)
        assert np.allclose(c.score(x), b.score(x)) and c.threshold == 0.4
        assert list(c.hint(x)) == list(b.hint(x))
        assert set(c.hint(x)) <= {"coverable", "tight", "not_coverable"}
