"""Candidate lists for swaps and cover, and opening cover cascades.

Until the validator (C2) exists, candidates come from a basic filter only: on the roster that
day, the role and qualifications the shift needs, no other working shift that day, not on
leave and not absent. Rest periods and monthly limits are NOT checked; every list says so.
"""

from datetime import date, timedelta

from dienstpilot.app.common import Department
from dienstpilot.app.deps import Ctx
from dienstpilot.app.roster import (
    Shift,
    approved_leave_days,
    effective,
    hours_for,
    month_end,
    month_start,
    span,
)
from dienstpilot.operations import service as operations
from dienstpilot.organization import service as organization
from dienstpilot.organization.service import StaffMember
from dienstpilot.shared.ports import CoverCandidate

ROLE_SHIFTS = {
    "chefaerztin": {"ruf"},
    "oberarzt": {"frueh", "ruf"},
    "facharzt": {"frueh", "spaet", "nacht", "bereitschaft"},
    "assistenzarzt": {"frueh", "spaet", "nacht", "bereitschaft"},
}
WORKING = {"frueh", "spaet", "nacht", "bereitschaft"}
CHECK = "unchecked"  # rule check (rest periods, limits) arrives with C2 in Phase 7


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
    """Return colleagues who pass the basic filter for a shift (unchecked against the rules)."""
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


def ranked(ctx: Ctx, dep: Department, people: list[StaffMember], day: date) -> list[CoverCandidate]:
    """Order candidates with the C5 stand-in (cover burden, then hours against contract)."""
    since = ctx.clock.now() - timedelta(days=90)
    covers: dict[str, int] = {}
    for c in operations.cascades(ctx.session, statuses=["closed"], since=since):
        if c.covered_by:
            covers[c.covered_by] = covers.get(c.covered_by, 0) + 1
    month = month_start(day)
    shifts = effective(ctx.session, month, month_end(month))
    ids = [p.id for p in people]
    leave = approved_leave_days(ctx.session, ids, month, month_end(month))
    holidays = set(organization.holidays(ctx.session, month, month_end(month)))
    rules = organization.rules_for(ctx.session, month).rules
    types = organization.shift_types(ctx.session)
    cands = []
    for p in people:
        h = hours_for(
            p, month, shifts, leave.get(p.id, set()), holidays, rules, types, ctx.clock.now()
        )
        cands.append(CoverCandidate(p.id, covers.get(p.id, 0), round(h.ratio, 3)))
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
        people = basic_candidates(ctx, dep, s, exclude={staff_id})
        order = [c.staff_id for c in ranked(ctx, dep, people, s.day)]
        c = operations.open_cascade(ctx.session, s.assignment_id, absence_id, order, now)
        opened.append(c.id)
    return opened
