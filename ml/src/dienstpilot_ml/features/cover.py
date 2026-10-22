"""C5 features for one cover offer, defined once for training, eval and serving.

Pure functions over dates, counts and shift codes; no staff identifiers, no input/output. The
definitions are the table in ``ml/cover_ranker/PROMOTION_RULE.md``. Age, gender, nationality,
family status and absence history are not inputs, and neither is any person identifier.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
from numpy.typing import NDArray

SHIFT_TYPES = ("frueh", "spaet", "nacht", "bereitschaft", "ruf")
NUMERIC = (
    "hours_ratio",
    "days_since_last_cover",
    "shifts_last_7d",
    "notice_hours",
    "weekday",
    "request_hour",
    "confirmed_pref",
)
FEATURES = ("shift_type", *NUMERIC)
# Hours a shift counts towards the contract (the rule set's credit for Bereitschaftsdienst).
CREDIT = {"frueh": 8.0, "spaet": 8.0, "nacht": 9.75, "bereitschaft": 18.0, "ruf": 0.0}
WORKING = ("frueh", "spaet", "nacht", "bereitschaft")
NO_COVER_DAYS = 365.0
MAX_NOTICE_HOURS = 72.0
PREF_WINDOW_DAYS = 365
PREF_LIMIT = 5.0
Matrix = NDArray[np.float64]


@dataclass(frozen=True)
class CoverFeatures:
    """The inputs of C5 for one candidate and one shift, at the moment of the request."""

    hours_ratio: float
    days_since_last_cover: float
    shifts_last_7d: float
    notice_hours: float
    shift_type: str
    weekday: int
    request_hour: float
    confirmed_pref: float


def month_contract_hours(weekly_hours: float, month: date) -> float:
    """Return the contract hours of a month: weekly hours / 5 for every weekday of the month."""
    d, n = month.replace(day=1), 0
    while d.month == month.month:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return weekly_hours / 5.0 * n


def credited_hours(shift_type: str) -> float:
    """Return the hours a shift counts towards the contract."""
    return CREDIT.get(shift_type, 0.0)


def notice_hours(asked_at: datetime, shift_start: datetime) -> float:
    """Return the hours from the request to the shift start, limited to 0 to 72."""
    return float(min(MAX_NOTICE_HOURS, max(0.0, (shift_start - asked_at).total_seconds() / 3600.0)))


def request_hour(asked_at: datetime) -> float:
    """Return the hour of the day of the request, minutes as a fraction."""
    return asked_at.hour + asked_at.minute / 60.0


def days_since(last: datetime | None, asked_at: datetime) -> float:
    """Return the days since the last cover (none: 365), capped at 365."""
    if last is None:
        return NO_COVER_DAYS
    return float(min(NO_COVER_DAYS, max(0.0, (asked_at - last).total_seconds() / 86400.0)))


def confirmed_pref(
    wishes: Iterable[tuple[date, str | None]],
    avoids: Iterable[tuple[date, str | None]],
    asked_on: date,
    shift_type: str,
) -> float:
    """Net confirmed preference for a shift type in the year before the request.

    Counts the person's own ``wish_work`` entries naming the shift minus their ``avoid_shift``
    entries naming it; limited to -5 to 5. Only entries the person entered or confirmed.
    """
    since = asked_on - timedelta(days=PREF_WINDOW_DAYS)
    wish = sum(1 for d, s in wishes if s == shift_type and since <= d < asked_on)
    avoid = sum(1 for d, s in avoids if s == shift_type and since <= d < asked_on)
    return float(max(-PREF_LIMIT, min(PREF_LIMIT, wish - avoid)))


def row(f: CoverFeatures) -> list[float]:
    """Return one feature row in ``FEATURES`` order; the shift type is its index in SHIFT_TYPES."""
    return [
        float(SHIFT_TYPES.index(f.shift_type)),
        f.hours_ratio,
        f.days_since_last_cover,
        f.shifts_last_7d,
        f.notice_hours,
        float(f.weekday),
        f.request_hour,
        f.confirmed_pref,
    ]


def matrix(rows: Iterable[CoverFeatures]) -> Matrix:
    """Return the feature matrix of several candidates."""
    return np.array([row(f) for f in rows], dtype=np.float64).reshape(-1, len(FEATURES))
