"""Roster bookkeeping shared by the planner, the in-month simulation and the demo gate.

A schedule maps person key → date → set of shift codes. A person holds at most one working
shift (frueh, spaet, nacht, bereitschaft) per day; Rufbereitschaft (ruf) is not working time
and may sit on the same day as a Frühdienst.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from synthdata.calendar import days, is_weekend, month_end, weekend_key
from synthdata.rules import RuleSet
from synthdata.shifts import WORKING, span
from synthdata.staff import Person

Schedule = dict[str, dict[date, set[str]]]

# Which roles may hold which shift (assumption, see ASSUMPTIONS.md).
ROLE_SHIFTS: dict[str, frozenset[str]] = {
    "chefaerztin": frozenset({"ruf"}),
    "oberarzt": frozenset({"frueh", "ruf"}),
    "facharzt": frozenset({"frueh", "spaet", "nacht", "bereitschaft"}),
    "assistenzarzt": frozenset({"frueh", "spaet", "nacht", "bereitschaft"}),
}
BANDED_ROLES = frozenset({"oberarzt", "facharzt", "assistenzarzt"})


def credit(code: str, rules: RuleSet) -> float:
    """Hours a shift counts towards the contract (Anrechnung for Bereitschaftsdienst)."""
    return {
        "frueh": 8.0,
        "spaet": 8.0,
        "nacht": 9.75,
        "bereitschaft": rules.bereitschaft_credited_hours,
    }.get(code, 0.0)


def workdays(month: date, holidays: set[date]) -> list[date]:
    """Monday–Friday days of the month that are not public holidays."""
    return [d for d in days(month, month_end(month)) if d.weekday() < 5 and d not in holidays]


@dataclass(frozen=True)
class Target:
    """Monthly contract hours and the leave credited towards them."""

    hours: float
    leave_credit: float
    workdays: int = 0


def month_target(p: Person, month: date, holidays: set[date], leave_days: set[date]) -> Target:
    """Contract hours for the days the person is on the department's roster this month."""
    hours = leave = 0.0
    n = 0
    for d in workdays(month, holidays):
        period = p.period_on(d)
        if period is None or p.on_rotation(d):
            continue
        per_day = period.weekly_hours / 5.0
        n += 1
        hours += per_day
        if d in leave_days:
            leave += per_day
    return Target(hours, leave, n)


def worked_hours(sched_p: dict[date, set[str]], month: date, rules: RuleSet) -> float:
    """Credited hours of the person's shifts in the month."""
    total = 0.0
    for d in days(month, month_end(month)):
        for code in sched_p.get(d, ()):
            total += credit(code, rules)
    return total


@dataclass(frozen=True)
class Violation:
    """One broken hard rule."""

    rule: str
    person: str | None
    day: date
    detail: str


def check_person(
    p: Person,
    sched_p: dict[date, set[str]],
    month: date,
    rules: RuleSet,
    holidays: set[date],
    blocked: set[date],
    leave_days: set[date],
    band: bool = True,
) -> list[Violation]:
    """Every hard rule that concerns one person, for the shifts in ``month``.

    ``sched_p`` may include days before the month, which count for rest periods, night
    sequences and the free day after Bereitschaftsdienst. ``blocked`` are days the person
    cannot work (leave, declared unavailability, known sickness).
    """
    out: list[Violation] = []
    last = month_end(month)
    weekends: set[date] = set()
    n_b = n_r = 0
    prev_end = None
    for d in days(month - timedelta(days=7), last):
        codes = sched_p.get(d, set())
        in_month = d >= month
        working = [c for c in codes if c in WORKING]
        if in_month and codes:
            role = p.role_on(d)
            if role is None or p.on_rotation(d):
                out.append(Violation("not_rostered", p.key, d, "nicht im Dienstplan der Abteilung"))
            else:
                for c in codes:
                    if c not in ROLE_SHIFTS[role]:
                        out.append(Violation("role", p.key, d, f"{c} nicht für {role}"))
                quals = p.qualifications_on(d)
                if "nacht" in codes and "nachtdienstfaehig" not in quals:
                    out.append(
                        Violation("qualification", p.key, d, "nacht ohne Nachtdienstfreigabe")
                    )
                if "bereitschaft" in codes and "nachtdienstfaehig" not in quals:
                    out.append(Violation("qualification", p.key, d, "bereitschaft ohne Freigabe"))
                if "ruf" in codes and "oberarzt" not in quals:
                    out.append(
                        Violation("qualification", p.key, d, "ruf ohne Oberarzt-Qualifikation")
                    )
            if d in blocked:
                out.append(
                    Violation("unavailable", p.key, d, "Urlaub, Abwesenheit oder 'kann nicht'")
                )
            if len(working) > 1:
                out.append(Violation("one_shift_per_day", p.key, d, ",".join(sorted(working))))
            if "ruf" in codes and any(c != "frueh" for c in working):
                out.append(Violation("one_shift_per_day", p.key, d, "ruf mit " + ",".join(working)))
            if is_weekend(d):
                weekends.add(weekend_key(d))
            n_b += "bereitschaft" in codes
            n_r += "ruf" in codes
            if rules.free_day_after_on_call and "bereitschaft" in sched_p.get(
                d - timedelta(days=1), set()
            ):
                out.append(
                    Violation(
                        "free_day_after_on_call", p.key, d, "Dienst am Tag nach Bereitschaftsdienst"
                    )
                )
        for c in sorted(working, key=lambda c: span(d, c)[0]):
            start, end = span(d, c)
            if prev_end is not None and in_month:
                rest = (start - prev_end).total_seconds() / 3600
                if rest < rules.min_rest_hours:
                    out.append(Violation("min_rest", p.key, d, f"Ruhezeit {rest:.1f} h"))
            prev_end = end
        if in_month and "nacht" in codes:
            run = 1
            k = d - timedelta(days=1)
            while "nacht" in sched_p.get(k, set()):
                run += 1
                k -= timedelta(days=1)
            if run > rules.max_consecutive_nights:
                out.append(Violation("max_consecutive_nights", p.key, d, f"{run} Nächte in Folge"))
    if len(weekends) > rules.max_weekends_per_month:
        out.append(Violation("max_weekends", p.key, month, f"{len(weekends)} Wochenenden"))
    if n_b > rules.max_on_call_per_month:
        out.append(Violation("max_on_call", p.key, month, f"{n_b} Bereitschaftsdienste"))
    if n_r > rules.max_on_call_home_per_month:
        out.append(Violation("max_on_call_home", p.key, month, f"{n_r} Rufbereitschaften"))
    if band:
        role = p.role_on(month_end(month)) or p.role_on(month)
        target = month_target(p, month, holidays, leave_days)
        if (
            role in BANDED_ROLES
            and target.hours > 0
            and target.workdays >= rules.contract_hours_band_min_days
        ):
            ratio = (worked_hours(sched_p, month, rules) + target.leave_credit) / target.hours
            lo, hi = rules.contract_hours_band
            if ratio > hi + 1e-9:
                out.append(Violation("contract_hours_band", p.key, month, f"{ratio:.0%} über Band"))
            if ratio < lo - 1e-9:
                out.append(
                    Violation("contract_hours_band", p.key, month, f"{ratio:.0%} unter Band")
                )
    return out


def coverage_violations(
    month: date,
    sched: Schedule,
    people: dict[str, Person],
    template: dict[date, list[tuple[str, str, int]]],
) -> list[Violation]:
    """Days and shifts where the assigned qualified physicians fall short of the demand."""
    out: list[Violation] = []
    for d in days(month, month_end(month)):
        holders: dict[str, list[set[str]]] = {}
        for key, sp in sched.items():
            for c in sp.get(d, ()):
                holders.setdefault(c, []).append(people[key].qualifications_on(d))
        for shift, qual, count in template[d]:
            qs = holders.get(shift, [])
            have = len(qs) if qual == "any" else sum(qual in q for q in qs)
            if have < count:
                out.append(Violation("coverage", None, d, f"{shift}/{qual}: {have} von {count}"))
    return out
