"""The CP-SAT model: hard rules as constraints, the rest as a weighted objective.

Decision variables x[p, d, s]: physician p works shift s on day d. Hours are scaled to quarter
hours so every quantity is an integer. A run solves one variant per weight profile; each later
variant must differ from the earlier ones in a minimum share of assignments.
"""

import math
import time as wall
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from ortools.sat.python import cp_model

from dienstpilot_solver.model import Config, Explanation, Metrics, Problem, Profile, Result, Variant

VERSION = "c1-1.0.1"  # 1.0.1: model built in a fixed order (reproducible across processes)
BERLIN = ZoneInfo("Europe/Berlin")
WORKING = ("frueh", "spaet", "nacht", "bereitschaft")
ALL = (*WORKING, "ruf")
# Tuples, not sets: the model must be built in the same order in every process (string hashing
# is randomised per process, and CP-SAT's search depends on the order of variables).
ROLE_SHIFTS: dict[str, tuple[str, ...]] = {
    "chefaerztin": ("ruf",),
    "oberarzt": ("frueh", "ruf"),
    "facharzt": WORKING,
    "assistenzarzt": WORKING,
}
Q = 4  # quarter hours
LABELS = "ABC"


def _month_days(m: date) -> list[date]:
    nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    return [m + timedelta(days=i) for i in range((nxt - m).days)]


def _span(p: Problem, d: date, s: str) -> tuple[datetime, datetime]:
    st = p.shifts[s]
    start = datetime.combine(d, st.start, tzinfo=BERLIN)
    end = datetime.combine(d + timedelta(days=1) if st.ends_next_day else d, st.end, tzinfo=BERLIN)
    return start.astimezone(UTC), end.astimezone(UTC)


def _credit(p: Problem, s: str) -> int:
    if s == "bereitschaft":
        return round(float(p.rules["bereitschaft_credited_hours"]) * Q)
    if s == "ruf":
        return 0
    return round(p.shifts[s].net_hours * Q)


class _Model:
    """One CP-SAT model of the month. Constraint groups can be guarded by assumption literals."""

    def __init__(self, p: Problem, cfg: Config, guarded: bool) -> None:
        self.p, self.cfg = p, cfg
        self.m = cp_model.CpModel()
        self.days = _month_days(p.month)
        self.guards: dict[cp_model.IntVar, Explanation] = {}
        self.guarded = guarded
        self.x: dict[tuple[str, date, str], cp_model.IntVar] = {}
        self.weekend_vars: dict[str, list[cp_model.IntVar]] = {}
        self.hours_expr: dict[str, tuple[Any, int, int]] = {}
        self.hist: dict[str, dict[date, set[str]]] = {}
        for sid, d, s in p.history:
            self.hist.setdefault(sid, {}).setdefault(d, set()).add(s)
        self._variables()
        self._hard()

    # -- helpers --
    def guard(self, key: str, **params: Any) -> cp_model.IntVar | None:
        """Return an enforcement literal for a constraint group (only when diagnosing)."""
        if not self.guarded:
            return None
        lit = self.m.new_bool_var(f"g{len(self.guards)}")
        self.guards[lit] = Explanation(key, params)
        return lit

    def add(self, ct: cp_model.Constraint, lit: cp_model.IntVar | None) -> None:
        if lit is not None:
            ct.only_enforce_if(lit)

    def vars(self, sid: str, d: date, shifts: tuple[str, ...] = ALL) -> list[cp_model.IntVar]:
        return [v for s in shifts if (v := self.x.get((sid, d, s))) is not None]

    def had(self, sid: str, d: date, s: str) -> bool:
        return s in self.hist.get(sid, {}).get(d, set())

    # -- variables: only where a person may hold the shift at all --
    def _variables(self) -> None:
        p = self.p
        mix: dict[str, dict[str, str]] = p.rules.get("qualification_mix", {})
        for sid, doc in sorted(p.doctors.items()):
            off = p.leave.get(sid, frozenset()) | p.blocked.get(sid, frozenset())
            for d in self.days:
                c = doc.contract(d)
                if c is None or not doc.available(d) or d in off:
                    continue
                if p.rules["free_day_after_on_call"] and self.had(sid, d - timedelta(days=1), "bereitschaft"):
                    continue
                for s in ROLE_SHIFTS[c[0]]:
                    need = mix.get(s, {}).get("all")
                    if need and not doc.holds(need, d):
                        continue
                    if not any(dem_s == s for dem_s, _, _ in p.demand.get(d, [])):
                        continue
                    self.x[(sid, d, s)] = self.m.new_bool_var(f"x_{sid[:6]}_{d:%d}_{s}")

    # -- hard rules --
    def _hard(self) -> None:
        p, m, rules = self.p, self.m, self.p.rules
        # Coverage: at least the demand per shift and qualification; Früh/Spät may exceed it a little.
        for d in self.days:
            totals: dict[str, int] = {}
            for s, q, n in p.demand.get(d, []):
                holders = [(sid, v) for (sid, dd, ss), v in self.x.items() if dd == d and ss == s]
                pool = [v for sid, v in holders if q == "any" or p.doctors[sid].holds(q, d)]
                lit = self.guard("infeasible.coverage", date=d.isoformat(), shift=s, qualification=q, required=n,
                                 available=len(pool))
                self.add(m.add(sum(pool) >= n), lit)
                if q == "any":
                    totals[s] = n
            for s, n in totals.items():
                pool = [v for (sid, dd, ss), v in self.x.items() if dd == d and ss == s]
                cap = n + (self.cfg.extra_day_shifts if s in ("frueh", "spaet") else 0)
                m.add(sum(pool) <= cap)
        for sid, doc in sorted(p.doctors.items()):
            if not any(k[0] == sid for k in self.x):
                continue
            g_rest = self.guard("infeasible.person", staff_id=sid, rule="min_rest")
            g_night = self.guard("infeasible.person", staff_id=sid, rule="max_consecutive_nights")
            g_week = self.guard("infeasible.person", staff_id=sid, rule="max_weekends")
            g_band = self.guard("infeasible.person", staff_id=sid, rule="contract_hours_band")
            for d in self.days:
                work = self.vars(sid, d, WORKING)
                m.add(sum(work) <= 1)
                ruf = self.x.get((sid, d, "ruf"))
                if ruf is not None:
                    for s in ("spaet", "nacht", "bereitschaft"):
                        if (v := self.x.get((sid, d, s))) is not None:
                            m.add(ruf + v <= 1)
                # Free day after Bereitschaftsdienst.
                b = self.x.get((sid, d, "bereitschaft"))
                if b is not None and rules["free_day_after_on_call"]:
                    for v in self.vars(sid, d + timedelta(days=1)):
                        m.add(b + v <= 1)
            # Rest: forbid pairs of working shifts on consecutive days closer than the minimum.
            prev_days = [self.days[0] - timedelta(days=1), *self.days]
            for d1, d2 in pairwise(prev_days):
                for s1 in WORKING:
                    for s2 in WORKING:
                        rest = (_span(p, d2, s2)[0] - _span(p, d1, s1)[1]).total_seconds() / 3600
                        if rest >= rules["min_rest_hours"]:
                            continue
                        v2 = self.x.get((sid, d2, s2))
                        if v2 is None:
                            continue
                        if d1 < self.days[0]:
                            if self.had(sid, d1, s1):
                                self.add(m.add(v2 == 0), g_rest)
                        elif (v1 := self.x.get((sid, d1, s1))) is not None:
                            self.add(m.add(v1 + v2 <= 1), g_rest)
            # Consecutive nights, continuing from the days before the month.
            n_max = int(rules["max_consecutive_nights"])
            window_days = [self.days[0] - timedelta(days=i) for i in range(n_max, 0, -1)] + self.days
            for i in range(len(window_days) - n_max):
                block = window_days[i : i + n_max + 1]
                fixed = sum(1 for d in block if d < self.days[0] and self.had(sid, d, "nacht"))
                vs = [v for d in block if d >= self.days[0] and (v := self.x.get((sid, d, "nacht"))) is not None]
                if vs and fixed + len(vs) > n_max:
                    self.add(m.add(sum(vs) <= n_max - fixed), g_night)
            # Weekends with any duty, Bereitschaft and Rufbereitschaft per month.
            weekends: dict[date, list[cp_model.IntVar]] = {}
            for d in self.days:
                if d.weekday() >= 5:
                    weekends.setdefault(d - timedelta(days=d.weekday() - 5), []).extend(self.vars(sid, d))
            wk = []
            for key, vs in weekends.items():
                if not vs:
                    continue
                w = m.new_bool_var(f"w_{sid[:6]}_{key:%d}")
                for v in vs:
                    m.add(w >= v)
                m.add(w <= sum(vs))
                wk.append(w)
            self.weekend_vars[sid] = wk
            if wk:
                self.add(m.add(sum(wk) <= int(rules["max_weekends_per_month"])), g_week)
            for c in p.commitments:
                if c.staff_id == sid:
                    m.add(sum(wk) >= c.weekends)
            bs = [v for d in self.days if (v := self.x.get((sid, d, "bereitschaft"))) is not None]
            if bs:
                m.add(sum(bs) <= int(rules["max_on_call_per_month"]))
            rs = [v for d in self.days if (v := self.x.get((sid, d, "ruf"))) is not None]
            if rs:
                m.add(sum(rs) <= int(rules["max_on_call_home_per_month"]))
            # Hours band (planned + leave credit within the band of the contract hours).
            target, leave_credit, applies = self.target(sid)
            hours = sum(_credit(p, s) * v for (pid, _, s), v in self.x.items() if pid == sid)
            self.hours_expr[sid] = (hours, target, leave_credit)
            if applies and target > 0:
                lo, hi = rules["contract_hours_band"]
                self.add(m.add(hours + leave_credit >= math.ceil(lo * target - 1e-9)), g_band)
                self.add(m.add(hours + leave_credit <= math.floor(hi * target + 1e-9)), g_band)

    def target(self, sid: str) -> tuple[int, int, bool]:
        """Return (contract quarter-hours, leave credit, band applies)."""
        doc, p = self.p.doctors[sid], self.p
        target = credit = 0.0
        workdays = 0
        banded = False
        for d in self.days:
            c = doc.contract(d)
            if c is None or not doc.available(d) or d.weekday() >= 5 or d in p.holidays:
                continue
            banded |= c[0] != "chefaerztin"
            workdays += 1
            target += c[1] / 5 * Q
            if d in p.leave.get(sid, frozenset()):
                credit += c[1] / 5 * Q
        return round(target), round(credit), banded and workdays >= int(p.rules["contract_hours_band_min_days"])

    # -- objective --
    def objective(self, prof: Profile, earlier: list[set[tuple[str, date, str]]]) -> dict[str, Any]:
        p, m, cfg = self.p, self.m, self.cfg
        terms: list[Any] = []
        # Wishes.
        unmet = []
        for w in p.wishes:
            shifts = ALL if w.shift is None else (w.shift,)
            vs = [v for s in shifts if (v := self.x.get((w.staff_id, w.day, s))) is not None]
            miss = m.new_bool_var("miss")
            if vs:
                m.add(sum(vs) + miss >= 1)
            else:
                m.add(miss == 1)
            unmet.append((miss, cfg.important_wish_weight if w.important else 1))
        terms += [prof.wishes * k * v for v, k in unmet]
        # "Rather not this shift" (soft): a penalty like one unmet wish, only when it is assigned.
        for a in p.avoid:
            if (v := self.x.get((a.staff_id, a.day, a.shift))) is not None:
                terms.append(prof.wishes * v)
        # Burden spread among specialists and residents (year to date + this month).
        wn, ww, wh = cfg.burden_weights
        loads = []
        for sid, doc in p.doctors.items():
            role = doc.contract(self.days[-1]) or doc.contract(self.days[0])
            if role is None or role[0] not in ("facharzt", "assistenzarzt") or not any(k[0] == sid for k in self.x):
                continue
            n0, w0, h0 = p.ytd.get(sid, (0, 0, 0))
            nights = sum(v for d in self.days if (v := self.x.get((sid, d, "nacht"))) is not None)
            hol = sum(v for d in self.days if d in p.holidays for v in self.vars(sid, d, WORKING))
            load = wn * (n0 + nights) + ww * (w0 + sum(self.weekend_vars.get(sid, []))) + wh * (h0 + hol)
            loads.append(load)
        hi = m.new_int_var(0, 10_000, "load_max")
        lo = m.new_int_var(0, 10_000, "load_min")
        for load in loads:
            m.add(hi >= load)
            m.add(lo <= load)
        spread = m.new_int_var(0, 10_000, "spread")
        m.add(spread == hi - lo)
        terms.append(prof.spread * Q * spread)
        # Overtime: planned + leave credit above the contract hours (quarter hours).
        overtime = []
        for _sid, (hours, target, credit) in self.hours_expr.items():
            if target <= 0:
                continue
            ot = m.new_int_var(0, 10_000, "ot")
            m.add(ot >= hours + credit - target)
            overtime.append(ot)
        terms.append(prof.overtime * sum(overtime))
        # Isolated single nights.
        iso = []
        for (sid, d, s), v in self.x.items():
            if s != "nacht":
                continue
            prev = self.x.get((sid, d - timedelta(days=1), "nacht"))
            nxt = self.x.get((sid, d + timedelta(days=1), "nacht"))
            before = 1 if d == self.days[0] and self.had(sid, d - timedelta(days=1), "nacht") else 0
            i = m.new_bool_var("iso")
            m.add(i >= v - (prev if prev is not None else before) - (nxt if nxt is not None else 0))
            iso.append(i)
        terms.append(prof.isolated_nights * Q * sum(iso))
        # Stability against a prior plan.
        changes = []
        prior = set(p.prior)
        if prior:
            for key, v in self.x.items():
                changes.append(1 - v if key in prior else v)
            terms.append(prof.stability * sum(changes))
        # Diversity: differ from every earlier variant in a minimum share of its assignments.
        for earlier_set in earlier:
            need = max(1, math.ceil(self.cfg.min_difference * len(earlier_set)))
            m.add(sum(1 - self.x[k] for k in sorted(earlier_set) if k in self.x) >= need)
        m.minimize(sum(terms))
        return {"unmet": unmet, "spread": spread, "hi": hi, "lo": lo, "overtime": overtime, "iso": iso,
                "changes": changes}


def _params(cfg: Config, single: bool = False) -> cp_model.CpSolver:
    s = cp_model.CpSolver()
    s.parameters.max_deterministic_time = cfg.deterministic_time
    s.parameters.max_time_in_seconds = cfg.max_wall_seconds
    s.parameters.random_seed = cfg.seed
    s.parameters.num_workers = 1 if single else cfg.workers
    s.parameters.interleave_search = not single  # deterministic multi-thread search
    return s


def solve(problem: Problem, cfg: Config | None = None) -> Result:
    """Return up to ``cfg.variants`` roster variants, or the reasons no valid roster exists."""
    cfg = cfg or Config()
    variants: list[Variant] = []
    earlier: list[set[tuple[str, date, str]]] = []
    config = {**asdict(cfg), "profiles": [asdict(p) for p in cfg.profiles]}
    for i, prof in enumerate(cfg.profiles[: cfg.variants]):
        mdl = _Model(problem, cfg, guarded=False)
        parts = mdl.objective(prof, earlier)
        solver = _params(cfg)
        t0 = wall.perf_counter()
        status = solver.solve(mdl.m)
        took = wall.perf_counter() - t0
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if i == 0:
                if status == cp_model.INFEASIBLE:
                    return Result("infeasible", (), tuple(explain(problem, cfg)), VERSION, config)
                return Result("unknown", (), (), VERSION, config)
            break  # no further variant that differs enough
        chosen = tuple(sorted(k for k, v in mdl.x.items() if solver.value(v)))
        earlier.append(set(chosen))
        variants.append(Variant(LABELS[i], prof.name, chosen, _metrics(problem, mdl, solver, parts, chosen),
                                "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE", solver.objective_value,
                                round(float(solver.deterministic_time), 3), round(took, 3)))
    return Result("ok", tuple(variants), (), VERSION, config)


def _metrics(p: Problem, mdl: _Model, solver: cp_model.CpSolver, parts: dict[str, Any],
             chosen: tuple[tuple[str, date, str], ...]) -> Metrics:
    unmet = parts["unmet"]
    wishes_total = len(unmet)
    granted = sum(1 for v, _ in unmet if not solver.value(v))
    important = [(v, k) for v, k in unmet if k > 1]
    ratios = {}
    for sid, (hours, target, credit) in mdl.hours_expr.items():
        if target > 0:
            ratios[sid] = round((solver.value(hours) + credit) / target, 3)
    overtime = sum(solver.value(o) for o in parts["overtime"]) / Q
    changes = len(set(chosen) ^ set(p.prior)) if p.prior else 0
    return Metrics(wishes_total, granted, len(important), sum(1 for v, _ in important if not solver.value(v)),
                   solver.value(parts["spread"]), solver.value(parts["lo"]), solver.value(parts["hi"]),
                   round(overtime, 2), sum(solver.value(i) for i in parts["iso"]), changes, ratios)


def explain(problem: Problem, cfg: Config) -> list[Explanation]:
    """Find a small set of rule groups that cannot hold together (sufficient assumptions)."""
    mdl = _Model(problem, cfg, guarded=True)
    mdl.m.add_assumptions(list(mdl.guards))
    solver = _params(cfg, single=True)
    status = solver.solve(mdl.m)
    if status != cp_model.INFEASIBLE:
        return [Explanation("infeasible.unknown", {})]
    core = solver.sufficient_assumptions_for_infeasibility()
    by_index = {g.Index(): e for g, e in mdl.guards.items()}
    out = [by_index[i] for i in core if i in by_index]
    return out[:5] or [Explanation("infeasible.unknown", {})]
