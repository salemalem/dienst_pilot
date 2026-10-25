"""The numeric grounding check: no number in an answer that the data does not stand behind.

A number (digits, decimals, percentages) or a date in the answer text is *grounded* if it equals
a number or date in the question, in a tool result of the same run, or in the result of a
``calculate`` call whose operands were themselves grounded. Names of months and weekdays are not
numbers; the year of any date in the data counts as a number, a day or month alone does not (a
date is compared as a whole). Anything else is ungrounded, and the application shows the labelled
fallback instead of the model's text.
"""

import re
from datetime import date
from typing import Any

from dienstpilot_agents.copilot.guard import ALIAS, UUID

MONTHS = {
    **{
        m: i + 1
        for i, m in enumerate(
            [
                "januar",
                "februar",
                "märz",
                "april",
                "mai",
                "juni",
                "juli",
                "august",
                "september",
                "oktober",
                "november",
                "dezember",
            ]
        )
    },
    **{
        m: i + 1
        for i, m in enumerate(
            [
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ]
        )
    },
}
_MONTH_WORD = "|".join(sorted(MONTHS, key=len, reverse=True))
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DOT = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b")
DE_LONG = re.compile(rf"\b(\d{{1,2}})\.?\s+({_MONTH_WORD})\s+(\d{{4}})\b", re.IGNORECASE)
EN_LONG = re.compile(
    rf"\b({_MONTH_WORD})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE
)
NUMBER = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?:\s?%)?(?![\w])")
DE_SHORT = re.compile(rf"\b(\d{{1,2}})\.?\s+({_MONTH_WORD})\b", re.IGNORECASE)
EN_SHORT = re.compile(rf"\b({_MONTH_WORD})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE)
MonthDay = tuple[str, int, int]  # a day and month without a year: ("md", month, day)
Value = float | date | MonthDay


def _date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def extract(text: str) -> list[Value]:
    """Return the dates and numbers in a text (aliases, ids and month names are not numbers)."""
    text = UUID.sub(" ", text)
    text = ALIAS.sub(" ", text)
    found: list[Value] = []

    def take(rx: re.Pattern[str], order: tuple[int, int, int], months: bool = False) -> None:
        nonlocal text

        def sub(m: re.Match[str]) -> str:
            g = m.groups()
            parts = [int(MONTHS[x.lower()]) if months and not x.isdigit() else int(x) for x in g]
            y, mo, d = (parts[order[0]], parts[order[1]], parts[order[2]])
            dt = _date(y, mo, d)
            if dt is not None:
                found.append(dt)
                return " "
            return m.group(0)

        text = rx.sub(sub, text)

    take(ISO, (0, 1, 2))
    take(DOT, (2, 1, 0))
    take(DE_LONG, (2, 1, 0), months=True)
    take(EN_LONG, (2, 0, 1), months=True)

    def short(rx: re.Pattern[str], day_first: bool) -> None:
        nonlocal text

        def sub(m: re.Match[str]) -> str:
            a, b = m.groups()
            d, mo = (int(a), MONTHS[b.lower()]) if day_first else (int(b), MONTHS[a.lower()])
            found.append(("md", mo, d))
            return " "

        text = rx.sub(sub, text)

    short(DE_SHORT, True)
    short(EN_SHORT, False)
    for m in NUMBER.finditer(text):
        found.append(float(m.group(1).replace(",", ".")))
    return found


def values_in(data: Any) -> list[Value]:
    """Return the numbers and dates in a JSON document (ids contribute nothing)."""
    out: list[Value] = []
    if isinstance(data, bool):
        return out
    if isinstance(data, (int, float)):
        out.append(float(data))
    elif isinstance(data, str):
        if UUID.fullmatch(data):
            return out
        for v in extract(data):
            out.append(v)
            if isinstance(v, date):
                out.append(float(v.year))
                out.append(("md", v.month, v.day))
    elif isinstance(data, list):
        for x in data:
            out += values_in(x)
    elif isinstance(data, dict):
        for x in data.values():
            out += values_in(x)
    return out


class Pool:
    """The numbers and dates an answer may use."""

    def __init__(self, question: str) -> None:
        """Start with what the question itself says."""
        self._values: set[Value] = set()
        self.add(extract(question))

    def add(self, values: list[Value]) -> None:
        """Add grounded values."""
        for v in values:
            self._values.add(v)
            if isinstance(v, date):
                self._values.add(float(v.year))
                self._values.add(("md", v.month, v.day))

    def add_result(self, data: Any) -> None:
        """Add everything a tool result says."""
        self.add(values_in(data))

    def knows(self, value: float) -> bool:
        """Return whether a number is in the pool (tolerant to float noise)."""
        return any(isinstance(v, float) and abs(v - value) < 1e-9 for v in self._values)

    def ungrounded(self, text: str) -> list[Value]:
        """Return the numbers and dates in ``text`` that nothing in the pool backs."""
        bad: list[Value] = []
        for v in extract(text):
            if isinstance(v, (date, tuple)):
                if v not in self._values:
                    bad.append(v)
            elif not self.knows(v):
                bad.append(v)
        return bad
