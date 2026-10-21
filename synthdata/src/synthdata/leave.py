"""Leave requests, decided by the planner against concurrency limits.

Requests are planned per person and year and cluster in school holidays by a latent preference.

Only the planner's reason is stored for a decline. The requester's own reason is never
collected (data minimisation, ARCHITECTURE C7).
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from synthdata.behaviour import Latent
from synthdata.calendar import days, school_holiday_periods
from synthdata.config import DEMO_NOW, PARAMS, TZ
from synthdata.ids import uid
from synthdata.rng import Streams
from synthdata.roster import BANDED_ROLES
from synthdata.staff import Person

DECLINE_REASON_DE = "Zu viele überschneidende Urlaube in diesem Zeitraum."
DECLINE_SENIOR_REASON_DE = (
    "In diesem Zeitraum ist bereits eine Oberärztin oder ein Oberarzt im Urlaub."
)
BLOCK_PATTERNS = [(10, 10, 5, 5), (15, 10, 5), (10, 10, 10), (10, 5, 5, 5, 5)]


@dataclass
class LeaveRequest:
    """One request and its decision."""

    id: object
    staff_key: str
    start: date
    end: date
    submitted_at: datetime
    status: str  # pending | approved | declined
    decided_at: datetime | None
    decision_reason_code: str | None
    decision_reason: str | None
    previous_id: object | None = None  # the declined request this one follows up


@dataclass(frozen=True)
class LeaveOutcome:
    """Leave requests, approved days, and how the holiday clustering was calibrated."""

    requests: list[LeaveRequest]
    approved: dict[str, set[date]]
    affinity_scale: float
    first_request_decline_rate: float


def _block(start_monday: date, working_days: int) -> tuple[date, date]:
    weeks, rest = divmod(working_days, 5)
    end = (
        start_monday + timedelta(weeks=weeks, days=-3)
        if rest == 0
        else start_monday + timedelta(weeks=weeks, days=rest - 1)
    )
    return start_monday, end


def generate_leave(
    streams: Streams,
    people: list[Person],
    latents: dict[str, Latent],
    years: range,
    affinity_scale: float = 1.0,
) -> tuple[list[LeaveRequest], dict[str, set[date]]]:
    """Return all leave requests of the period and the approved leave days per person.

    ``affinity_scale`` multiplies each person's latent holiday-period preference (capped at 1);
    it is the knob the calibration turns to reach the target decline rate.
    """
    wishes: list[tuple[datetime, str, date, date]] = []
    for p in people:
        affinity = min(1.0, latents[p.key].holiday_period_affinity * affinity_scale)
        for year in years:
            rng = streams.get("leave", p.key, year)
            employed = [
                d for d in days(date(year, 1, 1), date(year, 12, 31)) if p.role_on(d) is not None
            ]
            if len(employed) < 60:
                continue
            share = len(employed) / 365.0
            pattern = BLOCK_PATTERNS[int(rng.integers(0, len(BLOCK_PATTERNS)))]
            budget = round(PARAMS.leave_days_per_year * share)
            taken: list[tuple[date, date]] = []
            periods = [(a, b) for a, b, _, _ in school_holiday_periods(year) if (b - a).days >= 10]
            for n in pattern:
                if budget < 5:
                    break
                n = min(n, budget)
                for _ in range(20):
                    if rng.random() < affinity and periods:
                        a, b = periods[int(rng.integers(0, len(periods)))]
                        lo = a - timedelta(days=a.weekday())
                        start = lo + timedelta(
                            weeks=int(rng.integers(0, max(1, (b - lo).days // 7)))
                        )
                    else:
                        start = date(year, 1, 1) + timedelta(days=int(rng.integers(7, 350)))
                        start -= timedelta(days=start.weekday())
                    a2, b2 = _block(start, n)
                    if a2.year != year or b2.year != year:
                        continue
                    if any(not (b2 < x or a2 > y) for x, y in taken):
                        continue
                    if (
                        p.role_on(a2) is None
                        or p.role_on(b2) is None
                        or p.on_rotation(a2)
                        or p.on_rotation(b2)
                    ):
                        continue
                    taken.append((a2, b2))
                    budget -= n
                    ahead = int(rng.integers(60, 151))
                    at = datetime.combine(
                        a2 - timedelta(days=ahead),
                        time(int(rng.integers(8, 21)), int(rng.integers(0, 60))),
                        tzinfo=TZ,
                    )
                    wishes.append((at, p.key, a2, b2))
                    break

    by_key = {p.key: p for p in people}
    approved: dict[str, set[date]] = {}
    count: dict[date, int] = {}
    senior: dict[date, int] = {}
    requests: list[LeaveRequest] = []
    for at, key, a, b in sorted(wishes, key=lambda w: (w[0], w[1])):
        rng = streams.get("leave-decision", key, a.isoformat())
        previous: object | None = None
        for attempt in range(4):
            if at > DEMO_NOW:
                break
            decided = datetime.combine(
                (at + timedelta(days=int(rng.integers(1, 11)))).date(),
                time(int(rng.integers(9, 17)), 0),
                tzinfo=TZ,
            )
            span_days = list(days(a, b))
            p = by_key[key]
            is_senior = p.role_on(a) in ("oberarzt", "chefaerztin")
            too_many = any(count.get(d, 0) >= PARAMS.max_concurrent_leave for d in span_days)
            too_many_senior = is_senior and any(
                senior.get(d, 0) >= PARAMS.max_concurrent_senior_leave for d in span_days
            )
            rid = uid("leave", key, a, attempt)
            if decided > DEMO_NOW:
                requests.append(
                    LeaveRequest(rid, key, a, b, at, "pending", None, None, None, previous)
                )
                break
            if too_many or too_many_senior:
                code = "senior_overlap" if too_many_senior else "overlap"
                reason = DECLINE_SENIOR_REASON_DE if too_many_senior else DECLINE_REASON_DE
                requests.append(
                    LeaveRequest(rid, key, a, b, at, "declined", decided, code, reason, previous)
                )
                previous = rid
                # Try again, shifted by a week (later, earlier, two weeks later).
                shift = timedelta(days=(7, -14, 21)[attempt]) if attempt < 3 else timedelta(0)
                a, b = a + shift, b + shift
                at = decided + timedelta(days=int(rng.integers(1, 5)))
                if p.role_on(b) is None or p.on_rotation(b) or p.on_rotation(a):
                    break
                continue
            requests.append(
                LeaveRequest(rid, key, a, b, at, "approved", decided, None, None, previous)
            )
            for d in span_days:
                approved.setdefault(key, set()).add(d)
                if p.role_on(d) in BANDED_ROLES or is_senior:
                    count[d] = count.get(d, 0) + 1
                if is_senior:
                    senior[d] = senior.get(d, 0) + 1
            break
    return requests, approved


def first_request_decline_rate(requests: list[LeaveRequest]) -> float:
    """Share of decided first requests (not follow-ups) that the planner declined."""
    first = [r for r in requests if r.previous_id is None and r.status != "pending"]
    return sum(r.status == "declined" for r in first) / len(first) if first else 0.0


def calibrated_leave(
    streams: Streams, people: list[Person], latents: dict[str, Latent], years: range
) -> LeaveOutcome:
    """Generate leave with the holiday clustering scaled to hit the target decline rate.

    Bisection on the scale (deterministic: every candidate uses the same random streams). If
    the target lies outside what the scale can reach, the nearest end is used; the achieved
    rate is recorded either way.
    """
    target = PARAMS.target_first_request_decline_rate
    lo, hi = 0.0, 4.0
    best: tuple[float, float, float] | None = None  # distance, scale, rate
    for _ in range(14):
        mid = (lo + hi) / 2
        reqs, _ = generate_leave(streams, people, latents, years, mid)
        rate = first_request_decline_rate(reqs)
        if best is None or abs(rate - target) < best[0]:
            best = (abs(rate - target), mid, rate)
        if rate > target:
            hi = mid
        else:
            lo = mid
    for edge in (0.0, 4.0):
        reqs, _ = generate_leave(streams, people, latents, years, edge)
        rate = first_request_decline_rate(reqs)
        if best is None or abs(rate - target) < best[0]:
            best = (abs(rate - target), edge, rate)
    assert best is not None
    scale = round(best[1], 4)
    reqs, approved = generate_leave(streams, people, latents, years, scale)
    return LeaveOutcome(reqs, approved, scale, first_request_decline_rate(reqs))
