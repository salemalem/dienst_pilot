"""The simulated manual planner: a greedy month builder with realistic imperfections.

It fills the hardest slots first, prefers people with the fewest hours so far, leans on a few
"reliable" people for weekends (uneven weekends), and reads only some of the wishes. It never
breaks a hard rule on purpose: when no eligible person is left, the slot stays a gap.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from synthdata.behaviour import Latent, Wish
from synthdata.calendar import days, is_weekend, month_end, weekend_key
from synthdata.config import PARAMS
from synthdata.demand import Slot, slots_for
from synthdata.roster import (
    BANDED_ROLES,
    ROLE_SHIFTS,
    Schedule,
    Violation,
    check_person,
    coverage_violations,
    credit,
    month_target,
)
from synthdata.rules import RuleSet
from synthdata.shifts import WORKING, span
from synthdata.staff import Person


@dataclass
class PlanInput:
    """Everything the planner knows when building a month."""

    month: date
    rules: RuleSet
    people: dict[str, Person]
    latents: dict[str, Latent]
    holidays: set[date]
    leave: dict[str, set[date]]  # approved leave days per person
    blocked: dict[str, set[date]]  # leave + "kann nicht" + known sickness
    wishes: dict[str, list[Wish]]  # request-window answers of respondents
    history: Schedule  # effective schedule before the month (rest periods, night runs)
    template: dict[date, list[tuple[str, str, int]]]


@dataclass
class PState:
    """Running per-person state while the month is filled day by day."""

    target: float
    leave_credit: float
    hours: float = 0.0
    last_end: datetime | None = None
    weekends: set[date] = field(default_factory=set)
    n_b: int = 0
    n_r: int = 0
    ratio_cap: float = 1.10
    # Contract hours and leave credit accrued up to and including each day (for pacing).
    accrued: dict[date, tuple[float, float]] = field(default_factory=dict)

    def pace(self, d: date) -> float:
        """Hours so far against the target accrued so far: below 1 means behind."""
        target, leave = self.accrued.get(d, (self.target, self.leave_credit))
        return (self.hours + leave) / target if target > 0 else 1.0


@dataclass
class PlanResult:
    """A planned month and what is wrong with it (ideally nothing)."""

    schedule: Schedule
    gaps: list[Violation]
    person_violations: list[Violation]

    @property
    def score(self) -> tuple[int, int]:
        """Lower is better: (gaps, other violations)."""
        return len(self.gaps), len(self.person_violations)


def plan_month(inp: PlanInput, rngs: list[np.random.Generator]) -> PlanResult:
    """Try one greedy pass per generator and keep the best result."""
    best: PlanResult | None = None
    for rng in rngs:
        res = _attempt(inp, rng)
        if best is None or res.score < best.score:
            best = res
        if best.score == (0, 0):
            break
    assert best is not None
    return best


def _attempt(inp: PlanInput, rng: np.random.Generator) -> PlanResult:
    month, rules = inp.month, inp.rules
    last = month_end(month)
    active = [
        k
        for k, p in inp.people.items()
        if any(p.role_on(d) is not None and not p.on_rotation(d) for d in days(month, last))
    ]
    sched: Schedule = {k: {} for k in active}
    state: dict[str, PState] = {}
    for k in active:
        p = inp.people[k]
        t = month_target(p, month, inp.holidays, inp.leave.get(k, set()))
        hi = (
            rules.contract_hours_band[1]
            if t.workdays >= rules.contract_hours_band_min_days
            else 9.99
        )
        st = PState(target=t.hours, leave_credit=t.leave_credit, ratio_cap=hi)
        st.accrued = _accrual(p, month, inp.holidays, inp.leave.get(k, set()))
        for d in days(month - timedelta(days=7), month - timedelta(days=1)):
            for c in inp.history.get(k, {}).get(d, ()):
                sched[k].setdefault(d, set()).add(c)
                if c in WORKING:
                    st.last_end = span(d, c)[1]
        state[k] = st

    read: dict[str, set[tuple[date, str | None]]] = {}
    for k, ws in inp.wishes.items():
        seen = read.setdefault(k, set())
        for w in ws:
            p_read = (
                PARAMS.planner_reads_important_wish if w.important else PARAMS.planner_reads_wish
            )
            if w.kind == "wish_work" and rng.random() < p_read:
                seen.add((w.day, w.shift))

    for d in days(month, last):
        for slot in slots_for(d, inp.holidays):
            best_key: str | None = None
            best_score = float("inf")
            for k in active:
                if not _eligible(inp, sched, state, k, slot):
                    continue
                s = _score(inp, sched, state, read, k, slot) + float(rng.normal(0, 0.06))
                if s < best_score:
                    best_key, best_score = k, s
            if best_key is None:
                continue  # a gap; counted by the coverage check below
            _assign(sched, state, best_key, slot, rules)

    _fill_gaps(inp, sched, state, active)
    _repair_low_hours(inp, sched, state, active)
    _top_up(inp, sched, state, active)
    month_sched = {k: {d: c for d, c in sp.items() if d >= month} for k, sp in sched.items()}
    full = {k: {**inp.history.get(k, {}), **sp} for k, sp in sched.items()}
    person_v: list[Violation] = []
    for k in active:
        person_v += check_person(
            inp.people[k],
            full[k],
            month,
            rules,
            inp.holidays,
            inp.blocked.get(k, set()),
            inp.leave.get(k, set()),
        )
    gaps = coverage_violations(month, month_sched, inp.people, inp.template)
    return PlanResult(month_sched, gaps, person_v)


def _eligible(
    inp: PlanInput, sched: Schedule, state: dict[str, PState], k: str, slot: Slot
) -> bool:
    p, d, shift, rules = inp.people[k], slot.day, slot.shift, inp.rules
    role = p.role_on(d)
    if role is None or p.on_rotation(d) or shift not in ROLE_SHIFTS[role]:
        return False
    if d in inp.blocked.get(k, set()) or not slot.needs <= p.qualifications_on(d):
        return False
    sp = sched[k]
    today = sp.get(d, set())
    if shift == "ruf":
        if today:
            return False
    elif any(c in WORKING for c in today) or (today and shift != "frueh"):
        return False
    if rules.free_day_after_on_call and "bereitschaft" in sp.get(d - timedelta(days=1), set()):
        return False
    st = state[k]
    if (
        is_weekend(d)
        and weekend_key(d) not in st.weekends
        and len(st.weekends) >= rules.max_weekends_per_month
    ):
        return False
    if shift == "bereitschaft" and st.n_b >= rules.max_on_call_per_month:
        return False
    if shift == "ruf" and st.n_r >= rules.max_on_call_home_per_month:
        return False
    if shift in WORKING:
        start, _ = span(d, shift)
        if (
            st.last_end is not None
            and (start - st.last_end).total_seconds() / 3600 < rules.min_rest_hours
        ):
            return False
        if shift == "nacht":
            run, prev = 1, d - timedelta(days=1)
            while "nacht" in sp.get(prev, set()):
                run += 1
                prev -= timedelta(days=1)
            if run > rules.max_consecutive_nights:
                return False
        planned = st.hours + st.leave_credit + credit(shift, rules)
        if role in BANDED_ROLES and st.target > 0 and planned / st.target > st.ratio_cap + 1e-9:
            return False
    return True


def _score(
    inp: PlanInput,
    sched: Schedule,
    state: dict[str, PState],
    read: dict[str, set[tuple[date, str | None]]],
    k: str,
    slot: Slot,
) -> float:
    st, d, shift = state[k], slot.day, slot.shift
    lat = inp.latents[k]
    if shift == "ruf":
        s = st.n_r * 0.15
        if "ruf" in sched[k].get(d - timedelta(days=1), set()) and is_weekend(d):
            s -= 0.4  # the same senior takes the whole weekend
        return s - (0.3 * lat.planner_favour if is_weekend(d) else 0.0)
    s = st.pace(d)
    wished = read.get(k, set())
    if (d, shift) in wished or (d, None) in wished:
        s -= 0.25
    if shift == "nacht" and "nacht" in sched[k].get(d - timedelta(days=1), set()):
        s -= 0.6  # keep night blocks together
    if is_weekend(d) or shift == "bereitschaft":
        s -= 0.25 * lat.planner_favour  # the planner's go-to people for weekends
        if is_weekend(d) and weekend_key(d) in st.weekends:
            s -= 0.3  # both days of one weekend rather than a second weekend
    if shift == "frueh" and inp.people[k].role_on(d) == "oberarzt":
        s -= 0.5  # seniors work days
    return s


def _accrual(
    p: Person, month: date, holidays: set[date], leave: set[date]
) -> dict[date, tuple[float, float]]:
    """Cumulative contract hours and leave credit per day; at least one day's worth of target."""
    out: dict[date, tuple[float, float]] = {}
    target = credit_leave = 0.0
    full = month_target(p, month, holidays, leave)
    for d in days(month, month_end(month)):
        period = p.period_on(d)
        if period is not None and not p.on_rotation(d) and d.weekday() < 5 and d not in holidays:
            target += period.weekly_hours / 5.0
            if d in leave:
                credit_leave += period.weekly_hours / 5.0
        out[d] = (max(target, full.hours / 20.0), credit_leave)
    return out


def _assign(sched: Schedule, state: dict[str, PState], k: str, slot: Slot, rules: RuleSet) -> None:
    d, shift = slot.day, slot.shift
    sched[k].setdefault(d, set()).add(shift)
    st = state[k]
    st.hours += credit(shift, rules)
    if is_weekend(d):
        st.weekends.add(weekend_key(d))
    if shift == "bereitschaft":
        st.n_b += 1
    if shift == "ruf":
        st.n_r += 1
    if shift in WORKING:
        st.last_end = span(d, shift)[1]


def _repair_low_hours(
    inp: PlanInput, sched: Schedule, state: dict[str, PState], active: list[str]
) -> None:
    """Move shifts from the busiest people to those below the contract-hours band.

    A shift moves only to someone who holds every qualification the giver holds for it, so the
    qualification mix of the day stays intact, and only if the receiver breaks no rule.
    """
    month = inp.month
    lo = inp.rules.contract_hours_band[0]

    def ratio(k: str) -> float:
        st = state[k]
        return (st.hours + st.leave_credit) / st.target if st.target > 0 else 1.0

    banded = [k for k in active if _banded(inp.people[k], month, state[k]) and state[k].target > 0]
    for _ in range(12):
        moved = False
        for u in sorted((k for k in banded if ratio(k) < lo), key=ratio):
            for o in sorted((k for k in banded if k != u), key=ratio, reverse=True):
                if ratio(u) >= lo or ratio(o) <= lo:
                    break
                for d, codes in sorted(sched[o].items()):
                    if ratio(u) >= lo:
                        break
                    if d < month:
                        continue
                    for c in sorted(codes & set(WORKING)):
                        if _try_move(inp, sched, state, o, u, d, c, lo):
                            moved = True
                            break
        if not moved:
            return


def _banded(p: Person, month: date, st: PState | None = None) -> bool:
    """Whether the contract-hours band applies to p in this month (any banded role held)."""
    if st is not None and st.ratio_cap > 9:
        return False  # too few rostered workdays this month for the band to apply
    return any(p.role_on(d) in BANDED_ROLES for d in days(month, month_end(month)))


def _top_up(inp: PlanInput, sched: Schedule, state: dict[str, PState], active: list[str]) -> None:
    """Give anyone still below the band extra day shifts beyond the minimum demand.

    Demand is a minimum (coverage means at least the required count), so an extra Früh- or
    Spätdienst is allowed; manual planners do this rather than leave a colleague short of
    contract hours.
    """
    month, rules = inp.month, inp.rules
    lo = rules.contract_hours_band[0]
    for k in active:
        p, st = inp.people[k], state[k]
        if not _banded(p, month, st) or st.target <= 0:
            continue
        for d in days(month, month_end(month)):
            if (st.hours + st.leave_credit) / st.target >= lo:
                break
            if d.weekday() >= 5 or d in inp.holidays or sched[k].get(d):
                continue
            for extra in ("frueh", "spaet"):
                trial = {x: set(v) for x, v in sched[k].items()}
                trial.setdefault(d, set()).add(extra)
                hist = {**{x: set(v) for x, v in inp.history.get(k, {}).items()}, **trial}
                if not check_person(
                    p,
                    hist,
                    month,
                    rules,
                    inp.holidays,
                    inp.blocked.get(k, set()),
                    inp.leave.get(k, set()),
                    band=False,
                ):
                    sched[k] = trial
                    st.hours += credit(extra, rules)
                    break


BASE_NEEDS = {
    "nacht": {"nachtdienstfaehig"},
    "bereitschaft": {"nachtdienstfaehig"},
    "ruf": {"oberarzt"},
}


def _fill_gaps(
    inp: PlanInput, sched: Schedule, state: dict[str, PState], active: list[str]
) -> None:
    """Close coverage gaps the greedy pass left, the way a planner reshuffles a day.

    First a free colleague takes the gap directly; otherwise a colleague moves from another
    shift that day into the gap and a free colleague takes the shift they left. A change is
    kept only if nobody involved breaks a rule and the day's coverage gets better.
    """
    month = inp.month
    for d in days(month, month_end(month)):
        for _ in range(6):
            gaps = _day_gaps(inp, sched, d)
            if not gaps or not _close_one(inp, sched, state, active, d, gaps):
                break


def _day_gaps(inp: PlanInput, sched: Schedule, d: date) -> list[tuple[str, str]]:
    """Return the (shift, qualification) rows of d's demand that are short."""
    holders: dict[str, list[set[str]]] = {}
    for k, sp in sched.items():
        for c in sp.get(d, ()):
            holders.setdefault(c, []).append(inp.people[k].qualifications_on(d))
    short = []
    for shift, qual, count in inp.template[d]:
        qs = holders.get(shift, [])
        have = len(qs) if qual == "any" else sum(qual in q for q in qs)
        if have < count:
            short.append((shift, qual))
    return short


def _ok(
    inp: PlanInput,
    sched: Schedule,
    state: dict[str, PState],
    k: str,
    trial: dict[date, set[str]],
    delta: float,
) -> bool:
    p = inp.people[k]
    full = {**{x: set(v) for x, v in inp.history.get(k, {}).items()}, **trial}
    if check_person(
        p,
        full,
        inp.month,
        inp.rules,
        inp.holidays,
        inp.blocked.get(k, set()),
        inp.leave.get(k, set()),
        band=False,
    ):
        return False
    st = state[k]
    return st.target <= 0 or (st.hours + st.leave_credit + delta) / st.target <= st.ratio_cap + 1e-9


def _close_one(
    inp: PlanInput,
    sched: Schedule,
    state: dict[str, PState],
    active: list[str],
    d: date,
    gaps: list[tuple[str, str]],
) -> bool:
    rules = inp.rules
    before = len(gaps)
    for shift, qual in gaps:
        needs = set(BASE_NEEDS.get(shift, set())) | ({qual} if qual != "any" else set())
        # Direct: a free colleague with the right qualifications.
        for k in active:
            if sched[k].get(d) or not needs <= inp.people[k].qualifications_on(d):
                continue
            trial = {x: set(v) for x, v in sched[k].items()}
            trial[d] = {shift}
            if _ok(inp, sched, state, k, trial, credit(shift, rules)):
                sched[k] = trial
                state[k].hours += credit(shift, rules)
                if len(_day_gaps(inp, sched, d)) < before:
                    return True
                sched[k][d].discard(shift)
                if not sched[k][d]:
                    del sched[k][d]
                state[k].hours -= credit(shift, rules)
        # Chain: p moves from another shift into the gap, q takes p's old shift.
        for p_key in active:
            old = {c for c in sched[p_key].get(d, set()) if c in WORKING and c != shift}
            if len(old) != 1 or not needs <= inp.people[p_key].qualifications_on(d):
                continue
            (left,) = old
            trial_p = {x: set(v) for x, v in sched[p_key].items()}
            trial_p[d] = (trial_p[d] - {left}) | {shift}
            if not _ok(
                inp, sched, state, p_key, trial_p, credit(shift, rules) - credit(left, rules)
            ):
                continue
            left_needs = _needs_of(inp.people[p_key], d, left)
            for q in active:
                if (
                    q == p_key
                    or sched[q].get(d)
                    or not left_needs <= inp.people[q].qualifications_on(d)
                ):
                    continue
                trial_q = {x: set(v) for x, v in sched[q].items()}
                trial_q[d] = {left}
                if not _ok(inp, sched, state, q, trial_q, credit(left, rules)):
                    continue
                saved_p, saved_q = sched[p_key], sched[q]
                sched[p_key], sched[q] = trial_p, trial_q
                if len(_day_gaps(inp, sched, d)) < before:
                    state[p_key].hours += credit(shift, rules) - credit(left, rules)
                    state[q].hours += credit(left, rules)
                    return True
                sched[p_key], sched[q] = saved_p, saved_q
    return False


def _needs_of(p: Person, d: date, shift: str) -> set[str]:
    q = p.qualifications_on(d)
    if shift == "nacht":
        return {"nachtdienstfaehig"}
    if shift == "bereitschaft":
        return {"nachtdienstfaehig"} | ({"facharzt"} & q)
    return set()


def _try_move(
    inp: PlanInput,
    sched: Schedule,
    state: dict[str, PState],
    o: str,
    u: str,
    d: date,
    c: str,
    lo: float,
) -> bool:
    rules = inp.rules
    if (state[o].hours - credit(c, rules) + state[o].leave_credit) / max(
        state[o].target, 1e-9
    ) < lo:
        return False
    if not _needs_of(inp.people[o], d, c) <= inp.people[u].qualifications_on(d):
        return False
    if any(x in WORKING for x in sched[u].get(d, set())):
        return False  # the receiver already works that day
    trial_u = {k: set(v) for k, v in sched[u].items()}
    trial_u.setdefault(d, set()).add(c)
    hist_u = {**{k: set(v) for k, v in inp.history.get(u, {}).items()}, **trial_u}
    v = check_person(
        inp.people[u],
        hist_u,
        inp.month,
        rules,
        inp.holidays,
        inp.blocked.get(u, set()),
        inp.leave.get(u, set()),
        band=False,
    )
    if (
        v
        or (state[u].hours + credit(c, rules) + state[u].leave_credit) / max(state[u].target, 1e-9)
        > rules.contract_hours_band[1]
    ):
        return False
    sched[o][d].discard(c)
    if not sched[o][d]:
        del sched[o][d]
    sched[u] = trial_u
    state[o].hours -= credit(c, rules)
    state[u].hours += credit(c, rules)
    return True
