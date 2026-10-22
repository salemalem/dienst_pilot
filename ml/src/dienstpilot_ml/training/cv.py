"""Rolling-origin cross-validation over 2021 to 2024. 2025 is never touched here."""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from numpy.typing import NDArray

from dienstpilot_ml.features.absence import (
    HORIZONS,
    MIN_ORIGIN,
    DailySeries,
    FeatureBuilder,
    Matrix,
    targets,
)

TRAIN_END = date(2024, 12, 31)
# Six expanding-window folds; test origins in [first, last].
FOLDS = (
    (date(2022, 1, 1), date(2022, 6, 30)),
    (date(2022, 7, 1), date(2022, 12, 31)),
    (date(2023, 1, 1), date(2023, 6, 30)),
    (date(2023, 7, 1), date(2023, 12, 31)),
    (date(2024, 1, 1), date(2024, 6, 30)),
    (date(2024, 7, 1), date(2024, 12, 31)),
)
TUNING_FOLDS = (0, 1, 2, 3)  # 2022 and 2023: hyperparameter tuning
CALIBRATION_FOLDS = (4, 5)  # 2024: conformal calibration


Mask = NDArray[np.bool_]


@dataclass(frozen=True)
class Rows:
    """Feature rows with their targets; origins and horizons are per row."""

    x: Matrix
    y: Matrix
    origin: list[date]
    horizon: Matrix

    def take(self, mask: Mask) -> "Rows":
        """Return the rows where ``mask`` is true."""
        idx = np.flatnonzero(mask)
        return Rows(self.x[idx], self.y[idx], [self.origin[i] for i in idx], self.horizon[idx])

    @property
    def target_date(self) -> list[date]:
        """Return the target day of every row."""
        return [o + timedelta(days=int(h)) for o, h in zip(self.origin, self.horizon, strict=True)]

    @property
    def origin_ordinal(self) -> Matrix:
        """Return the origin of every row as an ordinal day."""
        return np.array([o.toordinal() for o in self.origin], dtype=np.float64)


def make_rows(
    builder: FeatureBuilder,
    series: DailySeries,
    first: date,
    last: date,
    last_target: date,
) -> Rows:
    """Return every (origin, horizon) with origin in [first, last] and target <= last_target."""
    origins = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    origins = [o for o in origins if o >= MIN_ORIGIN]
    pairs = [(o, h) for o in origins for h in HORIZONS if o + timedelta(days=h) <= last_target]
    o_list = [p[0] for p in pairs]
    h = np.array([p[1] for p in pairs], dtype=np.float64)
    x = builder.rows(o_list, [int(v) for v in h])
    y = np.array([targets(series, [o], [int(hh)])[0] for o, hh in zip(o_list, h, strict=True)])
    return Rows(x, y, o_list, h)


def fold_masks(rows: Rows, fold: int) -> tuple[Mask, Mask]:
    """Return (train, test) masks; training targets lie before the first test origin."""
    start, end = FOLDS[fold]
    o = rows.origin_ordinal
    targets_ord = o + rows.horizon
    train = targets_ord < start.toordinal()
    test = (o >= start.toordinal()) & (o <= end.toordinal())
    return train, test
