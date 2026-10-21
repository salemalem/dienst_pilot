"""Public interface of the fairness context: the burden of nights, weekends and holidays.

Pure functions over assignments; the application layer supplies them. Phase 9 adds the
persisted burden ledger.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, median

WORKING = {"frueh", "spaet", "nacht", "bereitschaft"}
CATEGORIES = ("nights", "weekends", "holidays")


@dataclass(frozen=True)
class Burden:
    """Counts of one person in a period."""

    nights: int = 0
    weekends: int = 0
    holidays: int = 0

    def get(self, category: str) -> int:
        """Return the count of a category."""
        return int(getattr(self, category))


@dataclass(frozen=True)
class Distribution:
    """Department statistics of one category, without names."""

    category: str
    people: int
    mean: float
    median: float
    minimum: int
    maximum: int
    values: tuple[int, ...]  # sorted, anonymous


def burden(assignments: Iterable[tuple[str, date, str]], holidays: set[date]) -> dict[str, Burden]:
    """Count nights, weekends with any duty, and public holidays with a working shift per person."""
    nights: dict[str, int] = {}
    weekends: dict[str, set[date]] = {}
    hol: dict[str, set[date]] = {}
    for staff_id, d, shift in assignments:
        if shift == "nacht":
            nights[staff_id] = nights.get(staff_id, 0) + 1
        if d.weekday() >= 5:
            weekends.setdefault(staff_id, set()).add(d - timedelta(days=d.weekday() - 5))
        if d in holidays and shift in WORKING:
            hol.setdefault(staff_id, set()).add(d)
    people = set(nights) | set(weekends) | set(hol)
    return {
        p: Burden(nights.get(p, 0), len(weekends.get(p, set())), len(hol.get(p, set())))
        for p in people
    }


def distribution(counts: dict[str, Burden], people: Iterable[str], category: str) -> Distribution:
    """Department statistics of a category over the given people (zero if they had none)."""
    values = sorted(counts.get(p, Burden()).get(category) for p in people)
    if not values:
        return Distribution(category, 0, 0.0, 0.0, 0, 0, ())
    return Distribution(
        category,
        len(values),
        round(mean(values), 2),
        float(median(values)),
        values[0],
        values[-1],
        tuple(values),
    )
