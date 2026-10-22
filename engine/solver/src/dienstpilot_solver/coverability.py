"""The M5 decision: coverable, coverable with a trade-off, or not coverable.

One definition, used by the product (``backend/.../app/jobs.py``) and by the C6 label generator
(``eval/``), so a label is exactly what M5 would have answered. The function is pure: the caller
supplies the state through callbacks (problems, the solver, the validator, whether a month is
still open). Rules: synthdata ASSUMPTIONS §18.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

from dienstpilot_solver.model import Commitment, Problem, Result

TRADE_OFF_OVERTIME_HOURS = 8.0
TRADE_OFF_PEAK_BURDEN = 2  # weighted points (nights, weekends, holidays incl. the year so far)

Assignments = tuple[tuple[str, date, str], ...]


@dataclass(frozen=True)
class Callbacks:
    """What the decision needs from its surroundings."""

    problem: Callable[[date, dict[str, set[date]] | None], Problem]
    solve: Callable[[Problem], Result]
    month_open: Callable[[date], bool]  # still open for planning (not published, not past)
    valid: Callable[[date, Assignments], bool]  # the roster passes every hard rule (C2)
    weekend_limit: Callable[[date], int]


def month_start(d: date) -> date:
    """Return the first day of d's month."""
    return d.replace(day=1)


def days(a: date, b: date) -> set[date]:
    """Return the days from a to b, both included."""
    return {a + timedelta(days=i) for i in range((b - a).days + 1)}


def weekends(staff_id: str, assignments: Assignments) -> int:
    """Return the number of weekends on which the person has duty."""
    return len(
        {
            d - timedelta(days=d.weekday() - 5)
            for s, d, _ in assignments
            if s == staff_id and d.weekday() >= 5
        }
    )


def decide(
    cb: Callbacks,
    *,
    requester: str,
    start: date,
    end: date,
    pending: dict[str, set[date]],
    base: dict[str, Any],
) -> dict[str, Any]:
    """Return the M5 result for a leave within one month.

    ``pending`` are the colleagues' pending requests in the month (they count as leave in both
    solves, the cautious reading). ``base`` is merged into every result (versions, thresholds).
    """
    leave_month = month_start(start)
    extra = {**pending, requester: days(start, end)}
    # The leave first: if it is infeasible the answer does not depend on the baseline.
    with_leave = cb.solve(cb.problem(leave_month, extra))
    if with_leave.status != "ok":
        return {
            **base,
            "outcome": "not_coverable",
            "explanations": [{"key": e.key, "params": e.params} for e in with_leave.explanations],
        }
    without = cb.solve(cb.problem(leave_month, pending))
    if without.status != "ok":  # the month is hard even without this leave
        return {**base, "outcome": "coverable", "reason": "baseline_unsolved"}
    a, b = without.variants[0].metrics, with_leave.variants[0].metrics
    impact = {
        "overtime_hours_delta": round(b.overtime_hours - a.overtime_hours, 2),
        "peak_burden_delta": b.burden_max - a.burden_max,
    }
    base = {**base, "impact": impact}
    burdens = (
        impact["overtime_hours_delta"] > TRADE_OFF_OVERTIME_HOURS
        or impact["peak_burden_delta"] > TRADE_OFF_PEAK_BURDEN
    )
    if not burdens:
        return {**base, "outcome": "coverable"}
    # Covering it burdens colleagues: offer one extra weekend in the month before, if that month
    # is still open and stays within every hard rule (including the weekend limit).
    before = month_start(leave_month - timedelta(days=1))
    if not cb.month_open(before):
        return {**base, "outcome": "coverable", "reason": "previous_month_planned"}
    problem = cb.problem(before, None)
    prev = cb.solve(problem)
    if prev.status != "ok":
        return {**base, "outcome": "coverable", "reason": "previous_month_unsolved"}
    n_weekends = weekends(requester, prev.variants[0].assignments) + 1
    if n_weekends > cb.weekend_limit(before):
        return {**base, "outcome": "coverable", "reason": "weekend_limit"}
    committed = replace(
        problem, commitments=(*problem.commitments, Commitment(requester, n_weekends))
    )
    trade = cb.solve(committed)
    if trade.status != "ok":
        return {**base, "outcome": "coverable", "reason": "trade_off_infeasible"}
    if not cb.valid(before, trade.variants[0].assignments):
        return {**base, "outcome": "coverable", "reason": "trade_off_invalid"}
    return {
        **base,
        "outcome": "coverable_with_trade_off",
        "trade_off": {"month": before.isoformat(), "weekends": n_weekends},
    }
