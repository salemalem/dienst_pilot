"""In-month changes after publication: shift swaps, sickness and cover cascades.

This simulates the manual era. The planner checks only a share of changes against the rules
(``Params.manual_rule_check_rate``, a simulation parameter); unchecked changes can break a
hard rule. Every such breach is recorded in _truth/ so evaluation can compare against it.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np

from synthdata.behaviour import Latent, report_time, seasonal_factor
from synthdata.calendar import days, month_end
from synthdata.config import DEMO_NOW, PARAMS, TZ
from synthdata.ids import uid
from synthdata.roster import ROLE_SHIFTS, Schedule, Violation, check_person
from synthdata.rules import RuleSet
from synthdata.shifts import WORKING
from synthdata.staff import Person


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


@dataclass
class OpsLog:
    """Rows produced by the in-month simulation."""

    absences: list[dict[str, object]] = field(default_factory=list)
    swaps: list[dict[str, object]] = field(default_factory=list)
    cascades: list[dict[str, object]] = field(default_factory=list)
    offers: list[dict[str, object]] = field(default_factory=list)
    breaches: list[dict[str, object]] = field(default_factory=list)  # truth
    hazard: list[dict[str, object]] = field(default_factory=list)  # truth
    cover_history: dict[str, list[date]] = field(default_factory=dict)


@dataclass
class OpsContext:
    """What the in-month simulation needs for one month."""

    month: date
    rules: RuleSet
    people: dict[str, Person]
    latents: dict[str, Latent]
    holidays: set[date]
    leave: dict[str, set[date]]
    sick: dict[str, set[date]]  # all sick days so far, updated in place
    effective: Schedule  # updated in place
    # Published assignment id per current holder: re-keyed when a shift changes hands, so
    # every swap and cover refers to the published assignment it started from.
    assignment_ids: dict[tuple[str, date, str], object]
    publish_at: datetime
    waves: dict[int, tuple[float, float, float, float]]


def _relevant_needs(p: Person, d: date, shift: str) -> set[str]:
    """Qualifications a replacement must have to take over p's shift (keeps the mix intact)."""
    q = p.qualifications_on(d)
    if shift in ("nacht", "bereitschaft"):
        return {"nachtdienstfaehig"} | ({"facharzt"} & q if shift == "bereitschaft" else set())
    if shift == "ruf":
        return {"oberarzt"}
    return set()


def _free_candidates(
    ctx: OpsContext, d: date, shift: str, exclude: str, needs: set[str]
) -> list[str]:
    out = []
    for k, p in ctx.people.items():
        role = p.role_on(d)
        if k == exclude or role is None or p.on_rotation(d) or shift not in ROLE_SHIFTS[role]:
            continue
        if d in ctx.leave.get(k, set()) or d in ctx.sick.get(k, set()):
            continue
        if not needs <= p.qualifications_on(d):
            continue
        today = ctx.effective.get(k, {}).get(d, set())
        if shift == "ruf" and today:
            continue
        if shift != "ruf" and (any(c in WORKING for c in today) or (today and shift != "frueh")):
            continue
        out.append(k)
    return out


def _violations_if(ctx: OpsContext, k: str, d: date, shift: str) -> list[Violation]:
    trial = {
        dd: set(cc)
        for dd, cc in ctx.effective.get(k, {}).items()
        if dd >= ctx.month - timedelta(days=8)
    }
    trial.setdefault(d, set()).add(shift)
    blocked = ctx.leave.get(k, set()) | ctx.sick.get(k, set())
    return check_person(
        ctx.people[k], trial, ctx.month, ctx.rules, ctx.holidays, blocked, ctx.leave.get(k, set())
    )


def _move(ctx: OpsContext, frm: str | None, to: str | None, d: date, shift: str) -> None:
    if frm is not None and to is not None and (frm, d, shift) in ctx.assignment_ids:
        ctx.assignment_ids[(to, d, shift)] = ctx.assignment_ids.pop((frm, d, shift))
    if frm is not None:
        ctx.effective[frm][d].discard(shift)
        if not ctx.effective[frm][d]:
            del ctx.effective[frm][d]
    if to is not None:
        ctx.effective.setdefault(to, {}).setdefault(d, set()).add(shift)


def _person_violations(ctx: OpsContext, k: str) -> dict[tuple[str, date], Violation]:
    blocked = ctx.leave.get(k, set()) | ctx.sick.get(k, set())
    sp = {
        dd: set(cc)
        for dd, cc in ctx.effective.get(k, {}).items()
        if dd >= ctx.month - timedelta(days=8)
    }
    vs = check_person(
        ctx.people[k], sp, ctx.month, ctx.rules, ctx.holidays, blocked, ctx.leave.get(k, set())
    )
    return {(v.rule, v.day): v for v in vs}


def _apply_and_record(
    log: OpsLog,
    ctx: OpsContext,
    frm: str | None,
    to: str,
    d: date,
    shift: str,
    source: str,
    source_id: object,
) -> None:
    """Apply a change and record the hard rules it newly breaks for the receiving person."""
    before = _person_violations(ctx, to)
    _move(ctx, frm, to, d, shift)
    for key, v in _person_violations(ctx, to).items():
        if key not in before:
            log.breaches.append(
                {
                    "date": v.day,
                    "staff_id": ctx.people[to].id,
                    "rule": v.rule,
                    "detail": v.detail,
                    "source": source,
                    "source_id": source_id,
                }
            )


@dataclass(frozen=True)
class PendingSwap:
    """A swap offer, drawn when the month is published and settled at ``settle_at``."""

    offered_by: str
    day: date
    shift: str
    offered_at: datetime
    settle_at: datetime


def draw_swap_offers(ctx: OpsContext, rng: np.random.Generator) -> list[PendingSwap]:
    """Each person offers at most one disliked shift of the month.

    Offers are made and settled between publication and the start of the month, so every swap
    precedes the month's own sick reports (a simplification, see ASSUMPTIONS.md §13).
    """
    last = month_end(ctx.month)
    month_start = datetime.combine(ctx.month, time(0, 0), tzinfo=TZ)
    out: list[PendingSwap] = []
    for k in sorted(ctx.people):
        lat = ctx.latents[k]
        mine = [
            (d, c)
            for d, cs in ctx.effective.get(k, {}).items()
            if ctx.month <= d <= last
            for c in cs
            if c in WORKING
        ]
        if not mine or rng.random() >= lat.swap_propensity:
            continue
        mine.sort(key=lambda t: (lat.shift_affinity(t[0], t[1]), t[0], t[1]))
        d, shift = mine[0]
        earliest = ctx.publish_at + timedelta(days=1)
        latest = month_start - timedelta(days=2)
        if latest <= earliest:
            continue
        offered_at = (earliest + (latest - earliest) * float(rng.random())).replace(
            second=0, microsecond=0
        )
        settle_at = min(
            offered_at + timedelta(hours=float(rng.uniform(0.5, 48))),
            month_start - timedelta(minutes=1),
        )
        out.append(PendingSwap(k, d, shift, offered_at, settle_at.replace(second=0, microsecond=0)))
    return out


def settle_swap(ctx: OpsContext, log: OpsLog, rng: np.random.Generator, swap: PendingSwap) -> None:
    """Ask colleagues in random order; the first who accepts and passes the planner takes it."""
    k, d, shift = swap.offered_by, swap.day, swap.shift
    if swap.settle_at > DEMO_NOW:
        return  # not settled by the demo date: leave it out
    assignment_id = ctx.assignment_ids.get((k, d, shift))
    if assignment_id is None:
        return  # no longer theirs (covered away after a sick report)
    swap_id = uid("swap", k, d, shift)
    needs = _relevant_needs(ctx.people[k], d, shift)
    cands = _free_candidates(ctx, d, shift, k, needs)
    order = [cands[i] for i in rng.permutation(len(cands))] if cands else []
    accepted_by: str | None = None
    status = "expired"
    for c in order[:8]:
        p_acc = _sigmoid(ctx.latents[c].shift_affinity(d, shift) - 0.6)
        if rng.random() < p_acc:
            checked = rng.random() < PARAMS.manual_rule_check_rate
            if checked and _violations_if(ctx, c, d, shift):
                status = "rejected"  # the planner refuses this taker; the offer stays open
                continue
            accepted_by = c
            status = "accepted"
            break
    log.swaps.append(
        {
            "id": swap_id,
            "assignment_id": assignment_id,
            "offered_by": ctx.people[k].id,
            "offered_at": swap.offered_at,
            "accepted_by": None if accepted_by is None else ctx.people[accepted_by].id,
            "accepted_at": swap.settle_at if accepted_by is not None else None,
            "status": status,
            "approval": "planner",
        }
    )
    if accepted_by is not None:
        _apply_and_record(log, ctx, k, accepted_by, d, shift, "swap", swap_id)


Carried = tuple[str, date, date, datetime, object]  # person, start, end, reported, absence id


def run_before_month(
    ctx: OpsContext, log: OpsLog, rng: np.random.Generator, carried: list[Carried]
) -> None:
    """Process everything between publication and the month, in the order it happens.

    That is swaps, and cover for sickness reported after publication that reaches into the month.
    """
    swaps = [(sw.settle_at, 1, sw) for sw in draw_swap_offers(ctx, rng)]
    covers = [(c[3], 0, c) for c in carried if c[3] > ctx.publish_at]
    events: list[tuple[datetime, int, PendingSwap | Carried]] = [*swaps, *covers]
    for _, _, ev in sorted(events, key=lambda e: (e[0], e[1])):
        if isinstance(ev, PendingSwap):
            settle_swap(ctx, log, rng, ev)
            continue
        k, a, b, reported, absence_id = ev
        for sd in days(max(a, ctx.month), min(b, month_end(ctx.month))):
            for shift in sorted(ctx.effective.get(k, {}).get(sd, set())):
                cover_shift(ctx, log, rng, k, sd, shift, reported, absence_id)


def simulate_sickness(
    ctx: OpsContext,
    log: OpsLog,
    rng: np.random.Generator,
    last_day: date,
    on_new_absence: Callable[[str, date, date, datetime, object], None],
) -> None:
    """Draw each day's sick reports, then run the cover cascades in report-time order.

    All of a day's reports are drawn first, so nobody who reports sick that day is asked to
    cover, and every cascade starts after the report that caused it.
    """
    for d in days(ctx.month, min(month_end(ctx.month), last_day)):
        seasonal = seasonal_factor(d, ctx.waves)
        expected = 0.0
        reports: list[tuple[datetime, str, date, object]] = []
        for k in sorted(ctx.people):
            p = ctx.people[k]
            if (
                p.role_on(d) is None
                or p.on_rotation(d)
                or d in ctx.leave.get(k, set())
                or d in ctx.sick.get(k, set())
            ):
                continue
            hazard = PARAMS.sick_base_hazard * ctx.latents[k].sickness_frailty * seasonal
            recent = ctx.effective.get(k, {})
            after_nights = any(
                "nacht" in recent.get(d - timedelta(days=i), set())
                for i in range(1, PARAMS.post_night_days + 1)
            )
            if after_nights and "nacht" not in recent.get(d, set()):
                hazard *= PARAMS.post_night_hazard_factor
            expected += hazard
            if rng.random() >= hazard:
                continue
            length = 1 + min(
                int(rng.poisson(PARAMS.sick_mean_extra_days)), PARAMS.sick_max_days - 1
            )
            end = d + timedelta(days=length - 1)
            reported = report_time(rng, d)
            absence_id = uid("absence", k, d)
            log.absences.append(
                {
                    "id": absence_id,
                    "staff_id": p.id,
                    "start_date": d,
                    "end_date": end,
                    "category": "sick",
                    "reported_at": reported,
                }
            )
            on_new_absence(k, d, end, reported, absence_id)
            reports.append((reported, k, end, absence_id))
        for at, who, until, aid in sorted(reports, key=lambda r: (r[0], r[1])):
            for sd in days(d, until):
                for shift in sorted(ctx.effective.get(who, {}).get(sd, set())):
                    cover_shift(ctx, log, rng, who, sd, shift, at, aid)
        log.hazard.append(
            {"date": d, "expected_new_episodes": expected, "seasonal_factor": seasonal}
        )


def cover_shift(
    ctx: OpsContext,
    log: OpsLog,
    rng: np.random.Generator,
    sick: str,
    d: date,
    shift: str,
    opened_at: datetime,
    absence_id: object,
) -> None:
    """Run the manual cover cascade for one shift of a sick colleague and apply the outcome."""
    assignment_id = ctx.assignment_ids.pop((sick, d, shift), None)
    if assignment_id is None:
        return  # not a published assignment (cannot happen; every held shift has an origin)
    cascade_id = uid("cascade", sick, d, shift)
    needs = _relevant_needs(ctx.people[sick], d, shift)
    _move(ctx, sick, None, d, shift)
    cands = _free_candidates(ctx, d, shift, sick, needs)
    order = sorted(cands, key=lambda c: -ctx.latents[c].planner_favour + float(rng.normal(0, 0.8)))
    t = opened_at
    covered: str | None = None
    rank = 0
    for c in order:
        if rank >= PARAMS.max_cover_asks:
            break
        checked = rng.random() < PARAMS.manual_rule_check_rate
        if checked and _violations_if(ctx, c, d, shift):
            continue  # the planner sees the conflict and does not ask
        rank += 1
        asked = t + timedelta(minutes=int(rng.integers(3, 12)))
        lat = ctx.latents[c]
        recent = sum(1 for x in ctx_cover_history(log, c) if 0 <= (d - x).days <= 30)
        p_acc = _sigmoid(
            lat.cover_willingness
            + 0.4 * lat.shift_affinity(d, shift)
            - lat.cover_load_decay * recent
        )
        accepted = rng.random() < p_acc
        responded = asked + timedelta(minutes=int(rng.integers(2, 20)))
        response = "accepted" if accepted else ("declined" if rng.random() < 0.8 else "no_response")
        log.offers.append(
            {
                "id": uid("cover-offer", cascade_id, rank),
                "cascade_id": cascade_id,
                "staff_id": ctx.people[c].id,
                "rank": rank,
                "asked_at": asked,
                "responded_at": None if response == "no_response" else responded,
                "response": response,
            }
        )
        t = responded
        if accepted:
            covered = c
            break
    outcome = "covered"
    if covered is None:
        seniors = [
            c
            for c in _free_candidates(ctx, d, shift, sick, needs)
            if ctx.people[c].role_on(d) == "oberarzt"
        ]
        if shift == "frueh" and seniors:
            covered = seniors[int(rng.integers(0, len(seniors)))]
            outcome = "escalated_overtime"
        else:
            outcome = "locum" if rng.random() < 0.7 else "unfilled"
    closed = t + timedelta(minutes=int(rng.integers(5, 40)))
    log.cascades.append(
        {
            "id": cascade_id,
            "assignment_id": assignment_id,
            "absence_id": absence_id,
            "opened_at": opened_at,
            "closed_at": closed,
            "outcome": outcome,
            "covered_by": None if covered is None else ctx.people[covered].id,
        }
    )
    if covered is not None:
        ctx.assignment_ids[(covered, d, shift)] = assignment_id
        _apply_and_record(log, ctx, None, covered, d, shift, "cover", cascade_id)
        log.cover_history.setdefault(covered, []).append(d)
    elif outcome == "unfilled":
        log.breaches.append(
            {
                "date": d,
                "staff_id": None,
                "rule": "coverage",
                "detail": f"{shift} unbesetzt",
                "source": "cover",
                "source_id": cascade_id,
            }
        )


def ctx_cover_history(log: OpsLog, k: str) -> list[date]:
    """Return the days on which k covered for a sick colleague."""
    """Days on which k covered for a sick colleague."""
    return log.cover_history.get(k, [])
