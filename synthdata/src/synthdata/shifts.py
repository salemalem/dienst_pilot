"""The six shift types with the exact times from UI_SPEC §5, and their real time spans."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from synthdata.config import TZ


@dataclass(frozen=True)
class ShiftType:
    """A shift type. Codes match the design-token keys (``frei`` is leave / Urlaub)."""

    code: str
    letter_de: str
    letter_en: str
    name_de: str
    name_en: str
    start: time | None
    end: time | None
    ends_next_day: bool
    break_minutes: int
    net_hours: float
    kind: str  # work | on_call | on_call_home | leave
    counts_as_working_time: bool
    burden_weight: float


SHIFT_TYPES: dict[str, ShiftType] = {
    s.code: s
    for s in [
        ShiftType(
            "frueh",
            "F",
            "E",
            "Frühdienst",
            "Early shift",
            time(7, 30),
            time(16, 0),
            False,
            30,
            8.0,
            "work",
            True,
            1.0,
        ),
        ShiftType(
            "spaet",
            "S",
            "L",
            "Spätdienst",
            "Late shift",
            time(13, 30),
            time(22, 0),
            False,
            30,
            8.0,
            "work",
            True,
            1.0,
        ),
        ShiftType(
            "nacht",
            "N",
            "N",
            "Nachtdienst",
            "Night shift",
            time(21, 30),
            time(8, 0),
            True,
            45,
            9.75,
            "work",
            True,
            2.0,
        ),
        ShiftType(
            "bereitschaft",
            "B",
            "O",
            "Bereitschaftsdienst",
            "On-call duty (in-house)",
            time(8, 0),
            time(8, 0),
            True,
            0,
            24.0,
            "on_call",
            True,
            3.0,
        ),
        ShiftType(
            "ruf",
            "R",
            "H",
            "Rufbereitschaft",
            "On-call from home",
            time(16, 0),
            time(7, 30),
            True,
            0,
            0.0,
            "on_call_home",
            False,
            1.0,
        ),
        ShiftType(
            "frei", "U", "V", "Urlaub", "Leave", None, None, False, 0, 8.0, "leave", False, 0.0
        ),
    ]
}

# Shifts that occupy the physician in the building; at most one per day, rest periods apply.
WORKING = ("frueh", "spaet", "nacht", "bereitschaft")


def span(day: date, code: str) -> tuple[datetime, datetime]:
    """Start and end of a shift on ``day`` in UTC (so durations are correct across DST)."""
    st = SHIFT_TYPES[code]
    if st.start is None or st.end is None:
        raise ValueError(f"{code} has no clock times")
    start = datetime.combine(day, st.start, tzinfo=TZ)
    end_day = day + timedelta(days=1) if st.ends_next_day else day
    end = datetime.combine(end_day, st.end, tzinfo=TZ)
    return start.astimezone(UTC), end.astimezone(UTC)
