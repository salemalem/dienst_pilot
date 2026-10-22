"""C6 features for one leave request, defined once for training, eval and serving.

``build_facts`` condenses the department's state for the request window into plain counts
(``LeaveFacts``); ``features`` turns the facts into the model's inputs. The definitions are the
text of ``ml/leave_surrogate/PROMOTION_RULE.md``. No person identifier, age, gender, nationality,
family status, leave history, reason or sickness is an input; the facts hold counts, the
requester's role and qualification flags only.
"""

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

QUALS = ("facharzt", "nachtdienstfaehig", "oberarzt")
ROLES = ("assistenzarzt", "facharzt", "oberarzt", "chefaerztin")
WORKING = ("frueh", "spaet", "nacht", "bereitschaft")
NUMERIC = (
    "slack_min",
    "slack_mean",
    *(f"qual_slack_{q}_min" for q in QUALS),
    "approved_max",
    "approved_mean",
    "pending_max",
    "pending_mean",
    "overlapping_colleagues",
    "holidays",
    "school_days",
    "weekend_days",
    "length_days",
    "notice_days",
    "month",
    *(f"has_{q}" for q in QUALS),
)
FEATURES = ("role", *NUMERIC)
Matrix = NDArray[np.float64]


class Doctor(Protocol):
    """What the facts need to know about a physician (the solver's ``Doctor`` has it)."""

    def available(self, d: date) -> bool:
        """Return whether the physician is on the department's roster on d."""

    def contract(self, d: date) -> tuple[str, float] | None:
        """Return (role, weekly hours) on d."""

    def holds(self, q: str, d: date) -> bool:
        """Return whether the physician holds qualification q on d."""


@dataclass(frozen=True)
class DayFacts:
    """One day of the window, with the requester counted as absent."""

    slack: int  # people free for a shift minus the working headcount
    qual_slack: tuple[int, ...]  # per ``QUALS``: free holders minus the qualified headcount
    approved: int  # colleagues on approved leave
    pending: int  # colleagues with a pending request
    holiday: bool
    school: bool
    weekend: bool


@dataclass(frozen=True)
class LeaveFacts:
    """The state of the department around one request window."""

    start: date
    end: date
    notice_days: int
    role: str
    quals: tuple[str, ...]  # the requester's qualifications at the start, sorted
    overlapping: int  # distinct colleagues with leave on a day of the window
    days: tuple[DayFacts, ...]

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-able form (no identifiers)."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "notice_days": self.notice_days,
            "role": self.role,
            "quals": list(self.quals),
            "overlapping": self.overlapping,
            "days": [
                [
                    d.slack,
                    list(d.qual_slack),
                    d.approved,
                    d.pending,
                    int(d.holiday),
                    int(d.school),
                    int(d.weekend),
                ]
                for d in self.days
            ],
        }

    @staticmethod
    def from_json(j: Mapping[str, Any]) -> "LeaveFacts":
        """Return the facts written by ``to_json``."""
        return LeaveFacts(
            date.fromisoformat(j["start"]),
            date.fromisoformat(j["end"]),
            int(j["notice_days"]),
            str(j["role"]),
            tuple(j["quals"]),
            int(j["overlapping"]),
            tuple(
                DayFacts(s, tuple(q), a, p, bool(h), bool(sc), bool(w))
                for s, q, a, p, h, sc, w in j["days"]
            ),
        )


def build_facts(
    *,
    start: date,
    end: date,
    notice_days: int,
    requester: str,
    doctors: Mapping[str, Doctor],
    approved: Mapping[str, Collection[date]],
    pending: Mapping[str, Collection[date]],
    demand: Mapping[date, Sequence[tuple[str, str, int]]],
    holidays: Collection[date],
    school_days: Collection[date],
) -> LeaveFacts:
    """Count what the window looks like if the requester is away.

    ``approved`` and ``pending`` map colleagues to their leave days; pending requests count as
    absence in the slack (the product's cautious reading). ``demand`` rows are
    (shift, qualification, required count).
    """
    me = doctors[requester]
    role = (me.contract(start) or ("assistenzarzt", 0.0))[0]
    quals = tuple(sorted(q for q in QUALS if me.holds(q, start)))
    rows: list[DayFacts] = []
    overlapping: set[str] = set()
    d = start
    while d <= end:
        rows.append(_day(d, requester, doctors, approved, pending, demand, holidays, school_days))
        for s, ds in approved.items():
            if s != requester and d in ds:
                overlapping.add(s)
        for s, ds in pending.items():
            if s != requester and d in ds:
                overlapping.add(s)
        d += timedelta(days=1)
    return LeaveFacts(start, end, notice_days, role, quals, len(overlapping), tuple(rows))


def _day(
    d: date,
    requester: str,
    doctors: Mapping[str, Doctor],
    approved: Mapping[str, Collection[date]],
    pending: Mapping[str, Collection[date]],
    demand: Mapping[date, Sequence[tuple[str, str, int]]],
    holidays: Collection[date],
    school_days: Collection[date],
) -> DayFacts:
    n_app = sum(1 for s, ds in approved.items() if s != requester and d in ds)
    n_pen = sum(1 for s, ds in pending.items() if s != requester and d in ds)
    free = [
        (s, doc)
        for s, doc in doctors.items()
        if s != requester
        and doc.available(d)
        and d not in approved.get(s, ())
        and d not in pending.get(s, ())
    ]
    pool = sum(1 for _, doc in free if (doc.contract(d) or ("", 0.0))[0] != "chefaerztin")
    rows = demand.get(d, ())
    heads: dict[str, int] = {}
    need = dict.fromkeys(QUALS, 0)
    for shift, q, n in rows:
        if shift in WORKING:
            heads[shift] = max(heads.get(shift, 0), n)
        if q in need:
            need[q] += n
    qual_slack = tuple(sum(1 for _, doc in free if doc.holds(q, d)) - need[q] for q in QUALS)
    return DayFacts(
        pool - sum(heads.values()),
        qual_slack,
        n_app,
        n_pen,
        d in holidays,
        d in school_days,
        d.weekday() >= 5,
    )


@dataclass(frozen=True)
class LeaveFeatures:
    """The model's inputs for one request."""

    role: str
    values: tuple[float, ...]  # in ``NUMERIC`` order


def features(f: LeaveFacts) -> LeaveFeatures:
    """Return the model's inputs for the facts."""
    n = len(f.days)
    slack = [d.slack for d in f.days]
    app = [d.approved for d in f.days]
    pen = [d.pending for d in f.days]
    values = (
        float(min(slack)),
        sum(slack) / n,
        *(float(min(d.qual_slack[i] for d in f.days)) for i in range(len(QUALS))),
        float(max(app)),
        sum(app) / n,
        float(max(pen)),
        sum(pen) / n,
        float(f.overlapping),
        float(sum(d.holiday for d in f.days)),
        float(sum(d.school for d in f.days)),
        float(sum(d.weekend for d in f.days)),
        float(n),
        float(f.notice_days),
        float(f.start.month),
        *(float(q in f.quals) for q in QUALS),
    )
    return LeaveFeatures(f.role, values)


def matrix(rows: Iterable[LeaveFeatures]) -> Matrix:
    """Return the design matrix, columns in ``FEATURES`` order (role as its index in ``ROLES``)."""
    return np.array(
        [[float(ROLES.index(r.role)), *r.values] for r in rows], dtype=np.float64
    ).reshape(-1, len(FEATURES))
