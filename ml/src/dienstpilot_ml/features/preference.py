"""C4 events and opportunities per (weekday, shift) cell, defined once for training and serving.

Pure functions over dates and shift codes; no staff identifiers, no input/output. A cell is a
weekday (0 = Monday) and one of the four shift types people can wish for or swap away.
"""

import calendar
from collections.abc import Iterable
from datetime import date

import numpy as np
from numpy.typing import NDArray

SHIFTS = ("frueh", "spaet", "nacht", "bereitschaft")
N_CELLS = 7 * len(SHIFTS)
Counts = NDArray[np.float64]


def cell_index(day: date, shift: str | None) -> int | None:
    """Return the cell of a day and shift, or None when the shift is unnamed or not modelled."""
    if shift not in SHIFTS:
        return None
    return day.weekday() * len(SHIFTS) + SHIFTS.index(shift)


def cell_label(index: int) -> tuple[int, str]:
    """Return (weekday, shift) of a cell index."""
    return index // len(SHIFTS), SHIFTS[index % len(SHIFTS)]


def event_counts(events: Iterable[tuple[date, str | None]]) -> Counts:
    """Count events per cell; events without a modelled shift are ignored."""
    out = np.zeros(N_CELLS)
    for day, shift in events:
        i = cell_index(day, shift)
        if i is not None:
            out[i] += 1.0
    return out


def wish_opportunities(months: Iterable[date], unavailable: Iterable[date]) -> Counts:
    """Count the days a person could have wished for a shift in the request windows they answered.

    ``months`` holds the first day of each roster month of an answered window. A day the person
    marked "kann nicht" is not an opportunity. Bereitschaftsdienst is offered on weekends only.
    """
    blocked = set(unavailable)
    out = np.zeros(N_CELLS)
    for month in months:
        for d in range(1, calendar.monthrange(month.year, month.month)[1] + 1):
            day = date(month.year, month.month, d)
            if day in blocked:
                continue
            for shift in SHIFTS:
                if shift == "bereitschaft" and day.weekday() < 5:
                    continue
                out[day.weekday() * len(SHIFTS) + SHIFTS.index(shift)] += 1.0
    return out


def avoid_opportunities(assignments: Iterable[tuple[date, str]]) -> Counts:
    """Count a person's published assignments per cell (the shifts they could swap away)."""
    return event_counts(assignments)
