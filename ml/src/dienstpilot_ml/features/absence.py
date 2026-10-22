"""C3 features. Defined once; training, evaluation and serving import this module.

Everything here is department level (ADR-003): daily absence counts, calendar flags and the
number of night shifts. No staff identifier enters the module, and a test checks that the
features of a forecast origin do not change when data after the origin changes.

A row is one (origin, horizon) pair. The origin is the last fully observed day, and the target
day is ``origin + horizon`` with horizon 1 to 42.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from numpy.typing import NDArray

HORIZONS = tuple(range(1, 43))
SERIES_START = date(2021, 1, 1)
MIN_ORIGIN = SERIES_START + timedelta(days=90)  # the 91-day level needs 91 observed days
YEAR = 364  # whole weeks, so the weekday of the same day last year matches

FEATURE_NAMES = (
    "horizon",
    "dow",
    "month",
    "doy_sin1",
    "doy_cos1",
    "doy_sin2",
    "doy_cos2",
    "is_holiday",
    "is_school_holiday",
    "level_7",
    "level_28",
    "level_91",
    "count_origin",
    "last_year_7d",
    "last_year_29d",
    "night_load_7",
)
INDEX = {name: i for i, name in enumerate(FEATURE_NAMES)}

Matrix = NDArray[np.float64]


@dataclass(frozen=True)
class DailySeries:
    """Absent people per day from ``start`` on (department level)."""

    start: date
    values: NDArray[np.float64]

    @property
    def end(self) -> date:
        """Return the last day with a value."""
        return self.start + timedelta(days=len(self.values) - 1)


@dataclass(frozen=True)
class Calendar:
    """Public holidays and school holidays of the department's state (dates, no names)."""

    holidays: frozenset[date]
    school_holidays: frozenset[date]


def daily_counts(intervals: Iterable[tuple[date, date]], start: date, end: date) -> DailySeries:
    """Count, per day from start to end, how many absence intervals cover the day.

    Days after ``end`` are cut off, so an episode that is still running at ``end`` contributes
    only the days observed so far.
    """
    n = (end - start).days + 1
    values = np.zeros(n)
    for a, b in intervals:
        lo, hi = max(a, start), min(b, end)
        if lo <= hi:
            values[(lo - start).days : (hi - start).days + 1] += 1.0
    return DailySeries(start, values)


class FeatureBuilder:
    """Builds feature rows for origins whose observed history is in ``series``."""

    def __init__(
        self, series: DailySeries, calendar: Calendar, night_shifts: Mapping[date, int]
    ) -> None:
        """Keep the observed series, the calendar and the nights worked per day."""
        self.series = series
        self.calendar = calendar
        self.night_shifts = night_shifts
        self._cum = np.concatenate([[0.0], np.cumsum(series.values)])

    def _window(self, last: date, days: int) -> float:
        """Return the mean over the ``days`` days ending at ``last`` (NaN if before the start)."""
        hi = (last - self.series.start).days + 1
        lo = hi - days
        if lo < 0 or hi > len(self.series.values):
            return math.nan
        return float((self._cum[hi] - self._cum[lo]) / days)

    def seasonal(self, origin: date, target: date, window: int, years: int) -> float:
        """Return the mean count around the same weekday 1..years years back (NaN if unknown).

        ``window`` is the half-width in days of the centred window. Used by the seasonal-naive
        baseline (window 0, one year is the plain seasonal-naive) and as a feature.
        """
        vals = []
        for k in range(1, years + 1):
            centre = target - timedelta(days=YEAR * k)
            if centre + timedelta(days=window) > origin:
                return math.nan
            v = self._window(centre + timedelta(days=window), 2 * window + 1)
            if math.isnan(v):
                return math.nan
            vals.append(v)
        return float(np.mean(vals))

    def night_load(self, origin: date, days: int = 7) -> float:
        """Return the night shifts worked in the ``days`` days ending at the origin."""
        return float(sum(self.night_shifts.get(origin - timedelta(days=i), 0) for i in range(days)))

    def row(self, origin: date, horizon: int) -> list[float]:
        """Return the feature row for one (origin, horizon)."""
        if origin > self.series.end:
            raise ValueError("the origin is later than the observed series")
        target = origin + timedelta(days=horizon)
        doy = (target.timetuple().tm_yday - 1) / 365.25 * 2 * math.pi
        cal = self.calendar
        return [
            float(horizon),
            float(target.weekday()),
            float(target.month),
            math.sin(doy),
            math.cos(doy),
            math.sin(2 * doy),
            math.cos(2 * doy),
            float(target in cal.holidays),
            float(target in cal.school_holidays),
            self._window(origin, 7),
            self._window(origin, 28),
            self._window(origin, 91),
            self._window(origin, 1),
            self.seasonal(origin, target, 3, 1),
            self.seasonal(origin, target, 14, 1),
            self.night_load(origin),
        ]

    def matrix(self, origins: Sequence[date], horizons: Sequence[int] = HORIZONS) -> Matrix:
        """Return one row per (origin, horizon): every origin with every horizon."""
        return np.array([self.row(o, h) for o in origins for h in horizons], dtype=np.float64)

    def rows(self, origins: Sequence[date], horizons: Sequence[int]) -> Matrix:
        """Return one row per (origin, horizon) pair given as parallel sequences."""
        return np.array([self.row(o, h) for o, h in zip(origins, horizons, strict=True)])


def targets(series: DailySeries, origins: Sequence[date], horizons: Sequence[int]) -> Matrix:
    """Return the realised count for each (origin, horizon) row (NaN beyond the series)."""
    out = np.full(len(origins) * len(horizons), math.nan)
    i = 0
    for o in origins:
        for h in horizons:
            k = (o + timedelta(days=h) - series.start).days
            if 0 <= k < len(series.values):
                out[i] = series.values[k]
            i += 1
    return out
