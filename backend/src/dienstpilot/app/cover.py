"""Candidate lists for swaps and cover, auto-approval checks, and opening cover cascades.

A quick filter (on the roster that day, role and qualifications, no other working shift, not on
leave or absent) narrows the department down; then the validator (C2) checks the change for
each remaining colleague: rest periods, consecutive nights, weekends, on-call limits, the free
day after Bereitschaftsdienst, the hours band and the qualification mix. Every list says
``check: "validated"``.
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta

from dienstpilot.app.common import Department
from dienstpilot.app.deps import Ctx
from dienstpilot.app.engine_inputs import Inputs
from dienstpilot.app.roster import (
    Shift,
    approved_leave_days,
    effective,
    month_end,
    month_start,
    span,
)
from dienstpilot.operations import service as operations
from dienstpilot.organization import service as organization
from dienstpilot.organization.service import StaffMember
from dienstpilot.requests import service as requests
from dienstpilot.shared.ports import CoverCandidate
from dienstpilot.shared.settings import TZ
from dienstpilot_ml.features.cover import (
    confirmed_pref,
    credited_hours,
    days_since,
    month_contract_hours,
    notice_hours,
    request_hour,
)
from dienstpilot_validator import Assignment, Violation

ROLE_SHIFTS = {
    "chefaerztin": {"ruf"},
    "oberarzt": {"frueh", "ruf"},
    "facharzt": {"frueh", "spaet", "nacht", "bereitschaft"},
    "assistenzarzt": {"frueh", "spaet", "nacht", "bereitschaft"},
}
WORKING = {"frueh", "spaet", "nacht", "bereitschaft"}
CHECK = "validated"  # every candidate passed the validator (C2)


def needed_qualifications(holder: StaffMember | None, day: date, shift_type: str) -> set[str]:
    """Return the qualifications a replacement needs to keep the day's qualification mix."""
    if shift_type == "ruf":
        return {"oberarzt"}
    if shift_type in ("nacht", "bereitschaft"):
        needs = {"nachtdienstfaehig"}
        if (
            shift_type == "bereitschaft"
            and holder is not None
            and holder.qualified("facharzt", day)
        ):
            needs.add("facharzt")
        return needs
    return set()


def basic_candidates(
    ctx: Ctx, dep: Department, shift: Shift, exclude: set[str]
) -> list[StaffMember]:
    """Return colleagues who pass the quick filter for a shift (before the C2 check)."""
    day = shift.day
    holder = dep.staff.get(shift.planned_holder)
    needs = needed_qualifications(holder, day, shift.shift_type)
    same_day = effective(ctx.session, day, day)
    busy = {s.holder for s in same_day if s.holder and s.shift_type in WORKING}
    on_ruf = {s.holder for s in same_day if s.holder and s.shift_type == "ruf"}
    ids = list(dep.staff)
    leave = approved_leave_days(ctx.session, ids, day, day)
    absent = {a.staff_id for a in operations.absences(ctx.session, ids, day, day)}
    out = []
    for p in dep.rostered(day):
        role = p.role_on(day)
        if p.id in exclude or role is None or shift.shift_type not in ROLE_SHIFTS[role]:
            continue
        if not all(p.qualified(q, day) for q in needs):
            continue
        if p.id in busy or p.id in absent or day in leave.get(p.id, set()):
            continue
        if shift.shift_type == "ruf" and p.id in on_ruf:
            continue
        if shift.shift_type != "frueh" and shift.shift_type != "ruf" and p.id in on_ruf:
            continue
        out.append(p)
    return out


def change_violations(
    ctx: Ctx,
    inputs: Inputs,
    remove: Iterable[Assignment],
    add: Iterable[Assignment],
    people: set[str],
) -> list[Violation]:
    """Return the violations a change introduces for the given people or for coverage.

    The month of every changed day is checked, and the next month too when the change is in
    the last week (rest periods and night runs reach across the boundary).
    """
    remove, add = list(remove), list(add)
    months = set()
    for a in (*remove, *add):
        m = month_start(a.day)
        months.add(m)
        if a.day > month_end(m) - timedelta(days=7):
            months.add(month_start(month_end(m) + timedelta(days=1)))
    out = []
    for m in sorted(months):
        _, introduced = ctx.engines.validator.validate_change(inputs.month(m), remove, add)
        out += [v for v in introduced if v.staff_id is None or v.staff_id in people]
    return out


def valid_takers(
    ctx: Ctx, dep: Department, shift: Shift, exclude: set[str], inputs: Inputs | None = None
) -> list[StaffMember]:
    """Return colleagues who could take a shift without breaking a rule (C2-checked)."""
    inputs = inputs or Inputs(ctx.session, dep, ctx.clock.now())
    remove = [Assignment(shift.holder, shift.day, shift.shift_type)] if shift.holder else []
    return [
        p
        for p in basic_candidates(ctx, dep, shift, exclude)
        if not change_violations(
            ctx, inputs, remove, [Assignment(p.id, shift.day, shift.shift_type)], {p.id}
        )
    ]


def offerer_violations(ctx: Ctx, inputs: Inputs, shift: Shift) -> list[Violation]:
    """Return what giving the shift away breaks for its holder (e.g. the hours band)."""
    if not shift.holder:
        return []
    remove = [Assignment(shift.holder, shift.day, shift.shift_type)]
    return [
        v
        for v in change_violations(ctx, inputs, remove, [], {shift.holder})
        if v.staff_id == shift.holder
    ]


def exchange_changes(
    offered: Shift, offerer: str, counter: Shift, taker: str
) -> tuple[list[Assignment], list[Assignment]]:
    """Return (remove, add) for an exchange: the taker takes ``offered``, gives ``counter``."""
    remove = [
        Assignment(offerer, offered.day, offered.shift_type),
        Assignment(taker, counter.day, counter.shift_type),
    ]
    add = [
        Assignment(taker, offered.day, offered.shift_type),
        Assignment(offerer, counter.day, counter.shift_type),
    ]
    return remove, add


def exchange_options(
    ctx: Ctx, dep: Department, inputs: Inputs, offered: Shift, offerer: str, taker: str
) -> list[Shift]:
    """Return the taker's future shifts that make a valid exchange for both people (C2).

    The taker must pass the quick filter for the offered shift; the counter-shift is on
    another day, in the offered shift's month or the next.
    """
    if not any(p.id == taker for p in basic_candidates(ctx, dep, offered, exclude={offerer})):
        return []
    start = ctx.clock.today() + timedelta(days=1)
    end = month_end(month_end(offered.day) + timedelta(days=1))
    out = []
    for h in effective(ctx.session, start, end):
        if h.holder != taker or h.day == offered.day:
            continue
        remove, add = exchange_changes(offered, offerer, h, taker)
        if not change_violations(ctx, inputs, remove, add, {offerer, taker}):
            out.append(h)
    return out


def swap_escalation(introduced: list[Violation], offerer: str) -> str | None:
    """Return why a swap needs the Planner (None: C2 found nothing new)."""
    if not introduced:
        return None
    if all(v.rule == "contract_hours_band" and v.staff_id == offerer for v in introduced):
        return operations.HOURS_BAND
    return operations.RULE_VIOLATION


def ranked(
    ctx: Ctx, dep: Department, people: list[StaffMember], day: date, shift_type: str
) -> list[CoverCandidate]:
    """Order candidates with C5 (burden buckets, then P(accept) inside a bucket).

    The features are the shared definitions of ``dienstpilot_ml.features.cover``, computed as of
    the demo clock. Nothing but the order leaves this function: P(accept) stays inside C5.
    """
    now = ctx.clock.now()
    local = now.astimezone(TZ)
    month = month_start(day)
    covers: dict[str, list[datetime]] = {}
    for cas in operations.cascades(
        ctx.session, statuses=["closed"], since=now - timedelta(days=365)
    ):
        if cas.covered_by and cas.closed_at:
            covers.setdefault(cas.covered_by, []).append(cas.closed_at)
    held = effective(ctx.session, month, month_end(month))
    week = effective(ctx.session, day - timedelta(days=7), day - timedelta(days=1))
    start = span(organization.shift_types(ctx.session)[shift_type], day)[0]
    since90 = now - timedelta(days=90)
    cands = []
    for p in people:
        entries = requests.wishes_of(ctx.session, p.id)
        wishes = [(e.day, e.shift_type) for e in entries if e.kind == "wish_work"]
        avoids = [(e.day, e.shift_type) for e in entries if e.kind == "avoid_shift"]
        contract = p.contract_on(day)
        target = month_contract_hours(contract.weekly_hours if contract else 40.0, month)
        hours = sum(credited_hours(s.shift_type) for s in held if s.holder == p.id)
        mine = covers.get(p.id, [])
        cands.append(
            CoverCandidate(
                p.id,
                sum(1 for t in mine if t >= since90),
                round(hours / target, 3) if target else 0.0,
                days_since(max(mine) if mine else None, now),
                float(sum(1 for s in week if s.holder == p.id and s.shift_type in WORKING)),
                notice_hours(now, start),
                shift_type,
                day.weekday(),
                request_hour(local),
                confirmed_pref(wishes, avoids, local.date(), shift_type),
            )
        )
    return ctx.engines.cover_ranker.rank(cands)


def open_cascades_for(
    ctx: Ctx, dep: Department, staff_id: str, absence_id: str, start: date, end: date
) -> list[str]:
    """Open a cascade for each of the person's shifts in start..end that has not begun yet."""
    now = ctx.clock.now()
    types = organization.shift_types(ctx.session)
    opened = []
    for s in effective(ctx.session, start, end):
        if s.holder != staff_id:
            continue
        if span(types[s.shift_type], s.day)[0] <= now:
            continue  # already started; the Planner handles it directly
        people = valid_takers(ctx, dep, s, exclude={staff_id})
        order = [c.staff_id for c in ranked(ctx, dep, people, s.day, s.shift_type)]
        c = operations.open_cascade(
            ctx.session, s.assignment_id, absence_id, order, now, department_id=dep.id
        )
        opened.append(c.id)
    return opened
