from datetime import timedelta
from pathlib import Path

import pytest

from dienstpilot_ml.features.absence import FeatureBuilder
from dienstpilot_ml.training.cv import FOLDS, TRAIN_END, fold_masks, make_rows
from dienstpilot_ml.training.data import load
from dienstpilot_ml.training.pipeline import TEST_END, _truncate

DATA = Path(__file__).resolve().parents[2] / "data/synthetic/v1"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="needs the generated dataset")


def test_folds_are_temporal_and_never_reach_2025() -> None:
    ds = load(DATA, through=TEST_END)
    series = _truncate(ds.series, TRAIN_END)
    rows = make_rows(
        FeatureBuilder(series, ds.calendar, ds.night_shifts),
        series,
        series.start,
        TRAIN_END,
        TRAIN_END,
    )
    assert max(rows.target_date) <= TRAIN_END
    for k, (start, _end) in enumerate(FOLDS):
        train, test = fold_masks(rows, k)
        t_train = rows.take(train)
        t_test = rows.take(test)
        assert (
            max(t_train.target_date) < start
        )  # no training label at or after the first test origin
        assert min(t_test.origin) >= start
        assert not (train & test).any()
    assert FOLDS[0][0] >= series.start + timedelta(days=365)
    assert FOLDS[-1][1] == TRAIN_END


def test_training_reads_only_the_allowed_tables_and_checks_their_hashes() -> None:
    from dienstpilot_ml.training.data import FILES

    ds = load(DATA, through=TEST_END)
    assert set(ds.file_sha256) == set(FILES)
    assert not any("truth" in f for f in FILES)
