import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from dienstpilot_ml.features.preference import (
    N_CELLS,
    avoid_opportunities,
    cell_index,
    event_counts,
    wish_opportunities,
)
from dienstpilot_ml.preference_learner.models import (
    Bundle,
    bundle_sha256,
    load_bundle,
    save_bundle,
    suggest,
)

DATA = Path(__file__).resolve().parents[2] / "data/synthetic/v1"


def _bundle(kind: str = "hierarchical", kappa: float = 10.0) -> Bundle:
    m = np.full(N_CELLS, 0.05)
    return Bundle(kind, m, m.copy(), kappa, kappa, {})


def test_opportunities_skip_unavailable_days_and_weekday_bereitschaft() -> None:
    ops = wish_opportunities([date(2025, 3, 1)], [date(2025, 3, 3)])  # Mon 3 March blocked
    mon_frueh = cell_index(date(2025, 3, 3), "frueh")
    assert mon_frueh is not None and ops[mon_frueh] == 4  # five Mondays minus the blocked 3rd
    assert ops[cell_index(date(2025, 3, 3), "bereitschaft") or 0] == 0  # no weekday on-call
    sat = cell_index(date(2025, 3, 1), "bereitschaft")
    assert sat is not None and ops[sat] == 5  # five Saturdays in March 2025


def test_events_without_a_modelled_shift_are_ignored() -> None:
    c = event_counts(
        [(date(2025, 3, 3), None), (date(2025, 3, 3), "ruf"), (date(2025, 3, 3), "spaet")]
    )
    assert c.sum() == 1
    assert avoid_opportunities([(date(2025, 3, 3), "ruf")]).sum() == 0


def test_shrinkage_limits_are_the_two_baselines() -> None:
    k = np.zeros(N_CELLS)
    n = np.zeros(N_CELLS)
    k[0], n[0] = 3.0, 6.0
    pooled = _bundle("pooled").predict("wish", k, n)
    raw = _bundle("raw").predict("wish", k, n)
    strong = _bundle(kappa=1e9).predict("wish", k, n)
    weak = _bundle(kappa=1e-9).predict("wish", k, n)
    assert np.allclose(strong, pooled, atol=1e-6)
    assert weak[0] == pytest.approx(raw[0], abs=1e-6)
    assert raw[0] == 0.5


def test_a_new_person_gets_the_department_rates() -> None:
    zero = np.zeros(N_CELLS)
    b = _bundle()
    assert np.allclose(b.predict("avoid", zero, zero), 0.05)
    assert suggest(b, zero, zero, zero, zero) == []


def test_suggestion_policy() -> None:
    zero = np.zeros(N_CELLS)
    k, n = zero.copy(), zero.copy()
    k[5], n[5] = 5.0, 8.0  # swapped away 5 of 8 against a 5 % department rate
    s = suggest(_bundle(), zero, zero, k, n)
    assert [(x.kind, x.events, x.trials) for x in s] == [("avoid", 5, 8)]
    assert s[0].probability >= 0.8 and s[0].rate >= 2 * s[0].department_rate
    k1 = zero.copy()
    k1[5] = 1.0
    assert suggest(_bundle(), zero, zero, k1, n) == []  # one event is not enough
    assert suggest(_bundle("pooled"), zero, zero, k, n) == []  # no personal signal
    assert suggest(_bundle(), zero, zero, k, n) == s  # deterministic


def test_the_bundle_holds_department_level_numbers_only(tmp_path: Path) -> None:
    save_bundle(tmp_path, _bundle())
    doc = json.loads((tmp_path / "bundle.json").read_text())
    assert set(doc) == {
        "format", "kind", "shifts", "cells", "m_wish", "m_avoid", "kappa_wish",
        "kappa_avoid", "p_clip", "meta",
    }  # fmt: skip
    assert len(doc["m_wish"]) == N_CELLS
    assert load_bundle(tmp_path).kappa_wish == 10.0
    assert len(bundle_sha256(tmp_path)) == 64


@pytest.mark.skipif(not DATA.exists(), reason="needs the generated dataset")
def test_training_data_stops_at_2024_and_reads_only_the_listed_files() -> None:
    from dienstpilot_ml.training.c4 import TRAIN_END
    from dienstpilot_ml.training.c4_data import FILES, load

    d = load(DATA, through=TRAIN_END)
    assert max(max(ys) for ys in d.counts.values()) <= 2024
    assert all("_truth" not in f for f in FILES)
    assert set(d.file_sha256) == set(FILES)


@pytest.mark.skipif(not DATA.exists(), reason="needs the generated dataset")
def test_features_of_the_past_do_not_change_when_2025_is_added() -> None:
    from dienstpilot_ml.training.c4_data import load

    early = load(DATA, through=date(2024, 12, 31)).upto(2024)
    late = load(DATA, through=date(2025, 12, 31)).upto(2024)
    assert early.keys() <= late.keys()
    assert all(np.array_equal(early[s], late[s]) for s in early)
