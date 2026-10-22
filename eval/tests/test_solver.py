"""C1 on real months: every output passes C2; runs are reproducible; infeasibility is explained."""

import os
import subprocess
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
from dienstpilot_solver.model import AvoidIn, Config
from dienstpilot_solver.solve import solve
from dienstpilot_validator import Assignment, validate
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dienstpilot_eval.inputs import Data, MonthData, to_problem

FAST = Config(deterministic_time=2.0, variants=1)
MONTHS = [date(2024, 2, 1), date(2025, 3, 1), date(2025, 8, 1), date(2026, 11, 1)]


def _passes_c2(md: MonthData, assignments: tuple[tuple[str, date, str], ...]) -> list[str]:
    inp = replace(md.month, assignments=md.history + tuple(Assignment(*a) for a in assignments))
    return sorted({v.rule for v in validate(inp)})


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.sampled_from(MONTHS), st.data())
def test_every_solver_output_passes_c2(data: Data, m: date, draw: st.DataObject) -> None:
    md = data.month(m)
    staff = sorted({a.staff_id for a in md.published})
    days = sorted({a.day for a in md.published})
    # Perturb the month: extra "kann nicht" days for a few people.
    extra = draw.draw(st.lists(st.tuples(st.sampled_from(staff), st.sampled_from(days)), max_size=6))
    blocked = dict(md.month.blocked)
    for s, d in extra:
        blocked[s] = frozenset(blocked.get(s, frozenset()) | {d})
    md = replace(md, month=replace(md.month, blocked=blocked))
    res = solve(to_problem(md), FAST)
    if res.status == "infeasible":
        assert res.explanations  # a reason is always given
        return
    assert res.status == "ok" and res.variants
    for v in res.variants:
        assert _passes_c2(md, v.assignments) == [], v.label


def test_three_variants_differ_and_all_pass_c2(data: Data) -> None:
    md = data.month(date(2025, 3, 1))
    res = solve(to_problem(md), Config(deterministic_time=3.0, variants=3))
    assert [v.profile for v in res.variants] == ["wishes_first", "zero_overtime", "balanced"]
    sets = [set(v.assignments) for v in res.variants]
    for i in range(1, len(sets)):
        for j in range(i):
            assert len(sets[j] - sets[i]) >= 0.05 * len(sets[j])
    for v in res.variants:
        assert _passes_c2(md, v.assignments) == []
        assert 0 <= v.metrics.wish_rate <= 1


def test_runs_are_reproducible(data: Data) -> None:
    p = to_problem(data.month(date(2025, 3, 1)))
    a = solve(p, FAST).variants[0].assignments
    b = solve(p, FAST).variants[0].assignments
    assert a == b


_IN_A_FRESH_PROCESS = """
import hashlib, sys
from datetime import date
from pathlib import Path
from dienstpilot_solver.model import AvoidIn, Config
from dienstpilot_solver.solve import solve
from dienstpilot_eval.inputs import Data, to_problem
p = to_problem(Data(Path(sys.argv[1])).month(date(2025, 3, 1)))
res = solve(p, Config(deterministic_time=2.0))
print(hashlib.sha256(repr([v.assignments for v in res.variants]).encode()).hexdigest())
"""


def test_runs_are_reproducible_across_processes(seed_root: Path) -> None:
    """String hashing differs per process; the model must not depend on it."""
    out = []
    for hash_seed in ("1", "2"):
        r = subprocess.run(
            [sys.executable, "-c", _IN_A_FRESH_PROCESS, str(seed_root)],
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
            capture_output=True, text=True, check=True,
        )
        out.append(r.stdout.strip())
    assert out[0] == out[1]


def test_infeasibility_is_explained_with_a_coverage_sentence(data: Data) -> None:
    md = data.month(date(2025, 3, 1))
    day = date(2025, 3, 11)
    everyone = {s: frozenset({day}) for s in md.month.people}
    md = replace(md, month=replace(md.month, blocked=everyone))
    res = solve(to_problem(md), FAST)
    assert res.status == "infeasible"
    keys = {(e.key, e.params.get("date")) for e in res.explanations}
    assert ("infeasible.coverage", day.isoformat()) in keys
    assert all(e.params.get("available") == 0 for e in res.explanations if e.key == "infeasible.coverage")


@pytest.mark.parametrize("m", [date(2026, 11, 1)])
def test_commitments_bind(data: Data, m: date) -> None:
    md = data.month(m)
    kaya = next(s for s, n in data.names.items() if n == "Dr. Aylin Kaya")
    from dienstpilot_solver.model import Commitment

    res = solve(to_problem(md, commitments=(Commitment(kaya, 2),)), FAST)
    assert res.status == "ok"
    weekends = {d - timedelta(days=d.weekday() - 5) for s, d, _ in res.variants[0].assignments
                if s == kaya and d.weekday() >= 5}
    assert len(weekends) >= 2


def test_a_soft_avoid_never_blocks_and_only_moves_the_objective(data: Data) -> None:
    """"Rather not Spätdienst" on some days: same hard inputs, still valid, and the shift is
    assigned to that person no more often than before."""
    md = data.month(date(2025, 3, 1))
    base = to_problem(md)
    first = solve(base, FAST).variants[0]
    person = next(s for s, _, sh in first.assignments if sh == "spaet")
    mine = tuple((d, sh) for s, d, sh in first.assignments if s == person and sh == "spaet")
    avoid = tuple(AvoidIn(person, d, sh) for d, sh in mine)
    soft = replace(base, avoid=avoid)
    # Only the soft input differs; nothing is blocked or taken off the person's leave.
    assert replace(soft, avoid=()) == base
    assert soft.blocked == base.blocked and soft.leave == base.leave and soft.wishes == base.wishes
    res = solve(soft, FAST)
    assert res.status == "ok"
    v = res.variants[0]
    assert _passes_c2(md, v.assignments) == []  # still a rule-valid roster
    assert v.metrics.wishes_total == first.metrics.wishes_total  # wishes are counted as before
    kept = sum(1 for s, d, sh in v.assignments if s == person and (d, sh) in set(mine))
    assert kept < len(mine)  # the penalty moved at least one of them to somebody else
    assert any(s == person for s, _, _ in v.assignments)  # and the person still works
