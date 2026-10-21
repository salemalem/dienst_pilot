"""Dates: public holidays (computed), approximate school holidays, months, weekends."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Holiday:
    """A public holiday or one day of a school-holiday period."""

    day: date
    kind: str  # "public" | "school"
    name_de: str
    name_en: str


def easter_sunday(year: int) -> date:
    """Return Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def public_holidays(year: int) -> list[Holiday]:
    """Return the public holidays of the fictional setting (the NRW set, an assumption)."""
    e = easter_sunday(year)
    fixed = [
        (date(year, 1, 1), "Neujahr", "New Year's Day"),
        (e - timedelta(days=2), "Karfreitag", "Good Friday"),
        (e + timedelta(days=1), "Ostermontag", "Easter Monday"),
        (date(year, 5, 1), "Tag der Arbeit", "Labour Day"),
        (e + timedelta(days=39), "Christi Himmelfahrt", "Ascension Day"),
        (e + timedelta(days=50), "Pfingstmontag", "Whit Monday"),
        (e + timedelta(days=60), "Fronleichnam", "Corpus Christi"),
        (date(year, 10, 3), "Tag der Deutschen Einheit", "German Unity Day"),
        (date(year, 11, 1), "Allerheiligen", "All Saints' Day"),
        (date(year, 12, 25), "1. Weihnachtstag", "Christmas Day"),
        (date(year, 12, 26), "2. Weihnachtstag", "Boxing Day"),
    ]
    return [Holiday(d, "public", de, en) for d, de, en in sorted(fixed)]


def _monday_on_or_after(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


def school_holiday_periods(year: int) -> list[tuple[date, date, str, str]]:
    """Return approximate school-holiday periods (rule-based, not any state's real calendar)."""
    e = easter_sunday(year)
    summer_start = _monday_on_or_after(date(year, 6, 22) + timedelta(weeks=year % 4))
    autumn_start = _monday_on_or_after(date(year, 10, 11))
    return [
        (date(year, 1, 1), date(year, 1, 6), "Weihnachtsferien", "Christmas holidays"),
        (e - timedelta(days=6), e + timedelta(days=7), "Osterferien", "Easter holidays"),
        (summer_start, summer_start + timedelta(days=43), "Sommerferien", "Summer holidays"),
        (autumn_start, autumn_start + timedelta(days=13), "Herbstferien", "Autumn holidays"),
        (date(year, 12, 23), date(year, 12, 31), "Weihnachtsferien", "Christmas holidays"),
    ]


def days(start: date, end: date) -> Iterator[date]:
    """Yield every date from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def month_starts(first: date, last: date) -> list[date]:
    """Return the first day of every month from first's month to last's month."""
    out: list[date] = []
    m = date(first.year, first.month, 1)
    while m <= last:
        out.append(m)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


def month_end(m: date) -> date:
    """Return the last day of the month starting at m."""
    nxt = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def is_weekend(d: date) -> bool:
    """Return whether d is a Saturday or Sunday."""
    return d.weekday() >= 5


def weekend_key(d: date) -> date:
    """Return the Saturday of the weekend a Saturday or Sunday belongs to."""
    return d - timedelta(days=d.weekday() - 5)


def monday_on_or_before(d: date) -> date:
    """Return the Monday of d's ISO week."""
    return d - timedelta(days=d.weekday())
