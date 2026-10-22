"""Background jobs: solver runs (W3) and leave coverability checks with a trade-off (M5).

Each job takes a session, the engines and the clock, so the arq worker and the tests run the
same code. Every variant is checked by the validator (C2) before it is stored.
"""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from dienstpilot.app.common import Department
from dienstpilot.app.engine_inputs import Inputs
from dienstpilot.app.roster import month_end, month_start
from dienstpilot.engines.registry import Engines
from dienstpilot.organization import service as organization
from dienstpilot.planning import service as planning
from dienstpilot.requests import service as requests
from dienstpilot.shared.ports import Clock
from dienstpilot_solver.coverability import (
    TRADE_OFF_OVERTIME_HOURS,
    TRADE_OFF_PEAK_BURDEN,
    Assignments,
    Callbacks,
    days,
    decide,
)
from dienstpilot_solver.model import PROFILES, Config, Metrics, Problem, Result
from dienstpilot_validator import Assignment

LABELS = "ABCDEFGH"
RECOMMENDED_PROFILE = "balanced"  # the benchmark's recommended profile (eval/run_benchmark.py)
RUN_CONFIG = Config()
# M5: one balanced variant per question, shorter time (synthdata ASSUMPTIONS §18).
CHECK_CONFIG = Config(
    deterministic_time=5.0,
    variants=1,
    profiles=tuple(p for p in PROFILES if p.name == RECOMMENDED_PROFILE),
)
# When covering a leave counts as a burden for colleagues (synthdata ASSUMPTIONS §18).


def _department(session: Session, department_id: str) -> Department:
    members = organization.staff(session, department_id)
    return Department(department_id, {s.id: s for s in members})


def metrics_json(m: Metrics) -> dict[str, Any]:
    """Return a variant's metrics for storage and the API."""
    out = asdict(m)
    out["wish_rate"] = round(m.wish_rate, 4)
    out["important_rate"] = round(m.important_rate, 4)
    return out


def run_roster(
    session: Session, engines: Engines, clock: Clock, *, run_id: str, department_id: str
) -> None:
    """Solve a month, check every variant with C2 and store the drafts."""
    r = planning.run(session, run_id)
    if r is None or r.status != "queued":
        return  # idempotent: a re-delivered job does nothing
    planning.set_run_status(session, run_id, "running")
    session.commit()
    try:
        inputs = Inputs(session, _department(session, department_id), clock.now())
        result = engines.optimizer.solve(inputs.problem(r.roster_month), RUN_CONFIG)
        _store(session, engines, inputs, run_id, r.roster_month, result, clock)
    except Exception as e:  # recorded on the run; the Planner sees it in W3
        session.rollback()
        planning.set_run_status(session, run_id, "failed", now=clock.now(), error=repr(e)[:500])
    session.commit()


def _store(
    session: Session,
    engines: Engines,
    inputs: Inputs,
    run_id: str,
    month: date,
    result: Result,
    clock: Clock,
) -> None:
    versions: dict[str, Any] = {
        "solver_version": result.solver_version,
        "validator_version": engines.validator.info.version,
        "config": result.config,
    }
    if result.status != "ok":
        planning.set_run_status(
            session,
            run_id,
            "infeasible" if result.status == "infeasible" else "failed",
            now=clock.now(),
            explanations=[{"key": e.key, "params": e.params} for e in result.explanations],
            error=None if result.status == "infeasible" else "no solution within the time limit",
            **versions,
        )
        return
    stored = 0
    for v in result.variants:
        own = tuple(_assignment(a) for a in v.assignments)
        violations = engines.validator.validate(inputs.month(month, own))
        if violations:  # never store a variant C2 rejects (the property test says it cannot happen)
            continue
        planning.add_variant(
            session,
            run_id,
            LABELS[stored],
            v.profile,
            {**metrics_json(v.metrics), "status": v.status, "objective": v.objective},
            v.profile == RECOMMENDED_PROFILE,
            list(v.assignments),
        )
        stored += 1
    planning.set_run_status(
        session,
        run_id,
        "done" if stored else "failed",
        now=clock.now(),
        error=None if stored else "every variant failed the validator",
        **versions,
    )


def _assignment(a: tuple[str, date, str]) -> Assignment:
    return Assignment(*a)


def check_leave(
    session: Session, engines: Engines, clock: Clock, *, check_id: str, department_id: str
) -> None:
    """M5: is the leave coverable, and does it need a trade-off? (synthdata ASSUMPTIONS §18)."""
    chk = requests.check(session, check_id)
    if chk is None or chk.status != "queued":
        return
    requests.set_check(session, check_id, "running")
    session.commit()
    try:
        result = _coverability(session, engines, clock, chk, department_id)
        requests.set_check(session, check_id, "done", result)
    except Exception as e:
        session.rollback()
        requests.set_check(session, check_id, "failed", {"error": repr(e)[:500]})
    session.commit()


def _coverability(
    session: Session,
    engines: Engines,
    clock: Clock,
    chk: requests.LeaveCheckInfo,
    department_id: str,
) -> dict[str, Any]:
    leave_month = month_start(chk.start_date)
    base: dict[str, Any] = {
        "leave_month": leave_month.isoformat(),
        "solver_version": engines.optimizer.info.version,
        "thresholds": {
            "overtime_hours": TRADE_OFF_OVERTIME_HOURS,
            "peak_burden": TRADE_OFF_PEAK_BURDEN,
        },
        "trade_off": None,
        "impact": None,
        "explanations": [],
    }
    if month_start(chk.end_date) != leave_month:
        return {**base, "outcome": "not_applicable", "reason": "spans_months"}
    if planning.published(session, leave_month) is not None:
        return {**base, "outcome": "not_applicable", "reason": "month_published"}
    dep = _department(session, department_id)
    inputs = Inputs(session, dep, clock.now())
    me = chk.staff_id
    # Colleagues' pending requests in the month count as leave too (the cautious reading).
    pending: dict[str, set[date]] = {}
    last = month_end(leave_month)
    others = [s for s in dep.staff if s != me]
    asked = requests.leave_requests(
        session, others, status="pending", overlapping=(leave_month, last)
    )
    for r in asked:
        pending.setdefault(r.staff_id, set()).update(
            days(max(r.start_date, leave_month), min(r.end_date, last))
        )
    base["pending_colleague_requests_counted"] = len(asked)
    today_month = month_start(clock.today())

    def problem(m: date, extra: dict[str, set[date]] | None) -> Problem:
        return inputs.problem(m, extra_leave=extra)

    def month_open(m: date) -> bool:
        return planning.published(session, m) is None and m > today_month

    def valid(m: date, assignments: Assignments) -> bool:
        month = inputs.month(m, tuple(_assignment(x) for x in assignments))
        return not engines.validator.validate(month)

    cb = Callbacks(
        problem=problem,
        solve=lambda p: engines.optimizer.solve(p, CHECK_CONFIG),
        month_open=month_open,
        valid=valid,
        weekend_limit=lambda m: int(
            organization.rules_for(session, m).rules["max_weekends_per_month"]
        ),
    )
    return decide(
        cb, requester=me, start=chk.start_date, end=chk.end_date, pending=pending, base=base
    )


JOBS: dict[str, Callable[..., None]] = {"run_roster": run_roster, "check_leave": check_leave}
