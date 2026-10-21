"""Staff app (M2–M12): everything a physician sees and does about themselves.

A physician sees their own roster, hours, fairness detail and requests, and the colleagues on
the same shift. Colleagues' hours and fairness detail are never returned here; fairness comes
with anonymous department statistics only.
"""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from dienstpilot.app.common import EngineLabel, department, label, record
from dienstpilot.app.context import CtxDep
from dienstpilot.app.cover import CHECK, basic_candidates, open_cascades_for
from dienstpilot.app.deps import Ctx, physician
from dienstpilot.app.roster import (
    Shift,
    approved_leave_days,
    credit,
    effective,
    hours_for,
    month_end,
    month_start,
    parse_month,
    span,
)
from dienstpilot.fairness import service as fairness
from dienstpilot.identity import service as identity
from dienstpilot.identity.service import UserView
from dienstpilot.operations import service as operations
from dienstpilot.organization import service as organization
from dienstpilot.planning import service as planning
from dienstpilot.requests import service as requests
from dienstpilot.shared.ports import EngineNotImplementedError

router = APIRouter(prefix="/me", tags=["staff app"])
Physician = Annotated[UserView, Depends(physician)]
MAX_IMPORTANT = 2


def _staff_id(c: Ctx) -> str:
    assert c.user.staff_id is not None
    return c.user.staff_id


class ShiftOut(BaseModel):
    """One shift of the signed-in physician."""

    assignment_id: str
    date: date
    shift_type: str
    starts_at: datetime | None
    ends_at: datetime | None
    changed: bool = Field(description="True if the shift came to this person by a swap or cover")


def _shift_out(c: Ctx, s: Shift) -> ShiftOut:
    st = organization.shift_types(c.session)[s.shift_type]
    start, end = span(st, s.day)
    return ShiftOut(
        assignment_id=s.assignment_id,
        date=s.day,
        shift_type=s.shift_type,
        starts_at=start,
        ends_at=end,
        changed=s.note in ("swap", "cover"),
    )


# --- M2 Heute / Today -------------------------------------------------------------------------


class Colleague(BaseModel):
    """A colleague on the same shift (no other detail)."""

    staff_id: str
    display_name: str


class NextShift(BaseModel):
    """The next shift and who else works it."""

    shift: ShiftOut
    colleagues: list[Colleague]


class WindowTask(BaseModel):
    """The open request window, if the person has not answered yet."""

    roster_month: date
    closes_at: datetime
    days_left: int


class CoverTask(BaseModel):
    """An open cover request to the person."""

    offer_id: str
    shift: ShiftOut
    deadline_at: datetime | None


class Today(BaseModel):
    """M2: next shift, open tasks."""

    now: datetime
    display_name: str
    next_shift: NextShift | None
    open_window: WindowTask | None
    cover_requests: list[CoverTask]


def _open_window_task(c: Ctx) -> WindowTask | None:
    for w in requests.windows(c.session):
        if w.status == "open" and w.closes_at > c.clock.now():
            if _staff_id(c) in requests.responses(c.session, w.id):
                return None
            days_left = (w.closes_at.astimezone(c.clock.now().tzinfo).date() - c.clock.today()).days
            return WindowTask(
                roster_month=w.roster_month, closes_at=w.closes_at, days_left=days_left
            )
    return None


def _cover_tasks(c: Ctx) -> list[CoverTask]:
    operations.advance(c.session, c.clock.now())
    out = []
    for offer, assignment_id in operations.pending_offers_for(c.session, _staff_id(c)):
        a = planning.assignment(c.session, assignment_id)
        if a is None:
            continue
        s = Shift(a.id, a.day, a.shift_type, None, a.staff_id, "open")
        out.append(
            CoverTask(offer_id=offer.id, shift=_shift_out(c, s), deadline_at=offer.deadline_at)
        )
    return out


@router.get("/today")
def today(c: CtxDep, _: Physician) -> Today:
    """M2: the next shift with colleagues, the open request window, open cover requests."""
    now, me = c.clock.now(), _staff_id(c)
    dep = department(c)
    shifts = effective(
        c.session, c.clock.today() - timedelta(days=1), c.clock.today() + timedelta(days=45)
    )
    types = organization.shift_types(c.session)
    mine = [s for s in shifts if s.holder == me and span(types[s.shift_type], s.day)[1] > now]
    nxt = None
    if mine:
        first = min(mine, key=lambda s: span(types[s.shift_type], s.day)[0])
        absent = {
            a.staff_id
            for a in operations.absences(c.session, list(dep.staff), first.day, first.day)
        }
        mates = [
            Colleague(staff_id=s.holder, display_name=dep.name(s.holder) or "")
            for s in shifts
            if s.day == first.day
            and s.shift_type == first.shift_type
            and s.holder
            and s.holder != me
            and s.holder not in absent
        ]
        nxt = NextShift(
            shift=_shift_out(c, first), colleagues=sorted(mates, key=lambda m: m.display_name)
        )
    return Today(
        now=now,
        display_name=c.user.display_name,
        next_shift=nxt,
        open_window=_open_window_task(c),
        cover_requests=_cover_tasks(c),
    )


# --- M3 Mein Dienstplan / My roster -----------------------------------------------------------


class RosterDay(BaseModel):
    """One day of the physician's month."""

    date: date
    shifts: list[ShiftOut]
    wish: Literal["granted", "missed"] | None


class MyRoster(BaseModel):
    """M3: the month as published and changed since."""

    roster_month: date
    published_at: datetime | None
    published_by: str | None
    rule_set_version: str | None
    days: list[RosterDay]


@router.get("/roster")
def my_roster(
    c: CtxDep, _: Physician, month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]
) -> MyRoster:
    """M3: the physician's month with wish marks (granted, missed)."""
    m, me = parse_month(month), _staff_id(c)
    pub = planning.published(c.session, m)
    if pub is None or (pub.published_at is not None and pub.published_at > c.clock.now()):
        return MyRoster(
            roster_month=m, published_at=None, published_by=None, rule_set_version=None, days=[]
        )
    shifts = [s for s in effective(c.session, m, month_end(m)) if s.holder == me]
    window = requests.window_for(c.session, m)
    wishes = requests.preferences(c.session, window.id, me) if window else []
    by_staff = identity.users_by_staff(c.session)
    approver = next(
        (u.display_name for u in by_staff.values() if u.staff_id == pub.approved_by), None
    )
    days = []
    d = m
    while d <= month_end(m):
        today_shifts = [s for s in shifts if s.day == d]
        mark: Literal["granted", "missed"] | None = None
        for w in wishes:
            if w.day == d and w.kind == "wish_work":
                ok = any(w.shift_type in (None, s.shift_type) for s in today_shifts)
                mark = "granted" if ok else "missed"
        days.append(RosterDay(date=d, shifts=[_shift_out(c, s) for s in today_shifts], wish=mark))
        d += timedelta(days=1)
    return MyRoster(
        roster_month=m,
        published_at=pub.published_at,
        published_by=approver,
        rule_set_version=pub.rule_set_version,
        days=days,
    )


# --- M4 Wünsche / Wishes ----------------------------------------------------------------------


class WishEntry(BaseModel):
    """A request-window entry."""

    date: date
    kind: Literal["unavailable", "wish_work"]
    shift_type: Literal["frueh", "spaet", "nacht", "bereitschaft", "ruf"] | None = None
    important: bool = False


class Suggestion(BaseModel):
    """A preference suggestion the person can confirm (C4)."""

    kind: str
    weekday: int
    shift_type: str
    evidence: int


class MyWishes(BaseModel):
    """M4: the open window and the person's answer."""

    roster_month: date
    closes_at: datetime
    days_left: int
    answered_at: datetime | None
    entries: list[WishEntry]
    max_important: int
    suggestions: list[Suggestion]
    suggestions_engine: EngineLabel


def _open_window(c: Ctx) -> requests.Window:
    for w in requests.windows(c.session):
        if w.status == "open" and w.closes_at > c.clock.now():
            return w
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No request window is open")


@router.get("/wishes")
def my_wishes(c: CtxDep, _: Physician) -> MyWishes:
    """M4: the open request window, the person's entries and preference suggestions."""
    w, me = _open_window(c), _staff_id(c)
    entries = [
        WishEntry(date=p.day, kind=p.kind, shift_type=p.shift_type, important=p.important)
        for p in requests.preferences(c.session, w.id, me)
    ]
    settings = identity.get_settings(c.session, c.user.id)
    suggestions: list[Suggestion] = []
    if settings["preference_suggestions"]:
        past = [
            (p.day, p.shift_type)
            for p in requests.wishes_of(c.session, me)
            if p.kind == "wish_work"
        ]
        given = [
            s
            for s in operations.swaps(c.session, staff_id=me)
            if s.offered_by == me and s.accepted_by
        ]
        away = []
        for s in given:
            a = planning.assignment(c.session, s.assignment_id)
            if a is not None:
                away.append((a.day, a.shift_type))
        suggestions = [Suggestion(**x.__dict__) for x in c.engines.preferences.suggest(past, away)]
    answered = requests.responses(c.session, w.id).get(me)
    return MyWishes(
        roster_month=w.roster_month,
        closes_at=w.closes_at,
        days_left=(w.closes_at.astimezone(c.clock.now().tzinfo).date() - c.clock.today()).days,
        answered_at=answered,
        entries=entries,
        max_important=MAX_IMPORTANT,
        suggestions=suggestions,
        suggestions_engine=label(c.engines.preferences.info),
    )


@router.put("/wishes")
def save_wishes(c: CtxDep, _: Physician, entries: list[WishEntry]) -> MyWishes:
    """M4: replace the person's answer to the open window (no approval needed, PROCESS §2)."""
    w, me = _open_window(c), _staff_id(c)
    if sum(e.important for e in entries) > MAX_IMPORTANT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"At most {MAX_IMPORTANT} important wishes"
        )
    if any(month_start(e.date) != w.roster_month for e in entries):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Every date must be in the window's month"
        )
    requests.submit(
        c.session,
        w.id,
        me,
        [requests.PreferenceEntry(me, e.date, e.kind, e.shift_type, e.important) for e in entries],
        c.clock.now(),
    )
    record(c, "preferences.submitted", "request_window", w.id, me, {"entries": len(entries)})
    return my_wishes(c, _)


class ParseRequest(BaseModel):
    """Free text to interpret (untrusted)."""

    text: str = Field(max_length=1000)
    language: Literal["de", "en"] = "de"


class ParsedOut(BaseModel):
    """C7: what was understood. Nothing is saved until the person confirms."""

    unavailable: list[date]
    prefer_shifts: list[str]
    avoid_shifts: list[str]
    avoid_weekends: bool
    clarifying_question: str | None
    engine: EngineLabel


@router.post("/wishes/parse")
def parse_wishes(c: CtxDep, _: Physician, body: ParseRequest) -> ParsedOut:
    """M4: interpret free text ("Wir haben verstanden: …"). The text is not stored."""
    w = _open_window(c)
    p = c.engines.intake.parse(body.text, w.roster_month, body.language)
    return ParsedOut(**p.__dict__, engine=label(c.engines.intake.info))


# --- M5 Urlaub / Leave ------------------------------------------------------------------------


class LeaveOut(BaseModel):
    """A leave request of the person. The Planner's reason is shown for a decline."""

    id: str
    start_date: date
    end_date: date
    submitted_at: datetime
    status: str
    decided_at: datetime | None
    decision_reason: str | None


class LeaveCheckIn(BaseModel):
    """Dates to check before submitting."""

    start_date: date
    end_date: date


class LeaveCheck(BaseModel):
    """M5: instant hint (C6) and what is known about overlaps."""

    outcome: str
    overlapping_colleagues: int
    max_on_leave_same_day: int
    limit: int
    leave_days_taken_this_year: int
    trade_off: None = Field(None, description="Confirmed trade-off needs C1 (Phase 7)")
    trade_off_available_from_phase: int = 7
    engine: EngineLabel


class LeaveIn(LeaveCheckIn):
    """A leave request. ``with_trade`` needs C1 and is refused until Phase 7."""

    with_trade: bool = False


LEAVE_LIMIT = 6  # concurrent approved leave the department plans with (synthdata ASSUMPTIONS §11)


def _leave_out(r: requests.LeaveRequest) -> LeaveOut:
    return LeaveOut(
        id=r.id,
        start_date=r.start_date,
        end_date=r.end_date,
        submitted_at=r.submitted_at,
        status=r.status,
        decided_at=r.decided_at,
        decision_reason=r.decision_reason,
    )


@router.get("/leave")
def my_leave(c: CtxDep, _: Physician) -> list[LeaveOut]:
    """M5: the person's leave requests."""
    return [_leave_out(r) for r in requests.leave_requests(c.session, [_staff_id(c)])]


def _days_taken(c: Ctx, me: str, year: int) -> int:
    start, end = date(year, 1, 1), date(year, 12, 31)
    days = approved_leave_days(c.session, [me], start, end).get(me, set())
    return sum(1 for d in days if d.weekday() < 5)


@router.post("/leave/check")
def check_leave(c: CtxDep, _: Physician, body: LeaveCheckIn) -> LeaveCheck:
    """M5: instant hint before submitting (C6 stand-in); the confirmed trade-off waits for C1."""
    if body.end_date < body.start_date or body.start_date <= c.clock.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose future dates, start before end"
        )
    dep, me = department(c), _staff_id(c)
    others = [s for s in dep.staff if s != me]
    per_day: dict[date, int] = {}
    for days in approved_leave_days(c.session, others, body.start_date, body.end_date).values():
        for d in days:
            per_day[d] = per_day.get(d, 0) + 1
    overlapping = {
        r.staff_id
        for r in requests.leave_requests(
            c.session, others, overlapping=(body.start_date, body.end_date)
        )
        if r.status in ("approved", "pending")
    }
    h = c.engines.leave.hint(body.start_date, body.end_date, per_day, LEAVE_LIMIT)
    return LeaveCheck(
        outcome=h.outcome,
        overlapping_colleagues=len(overlapping),
        max_on_leave_same_day=h.max_overlapping,
        limit=h.limit,
        leave_days_taken_this_year=_days_taken(c, me, body.start_date.year),
        engine=label(c.engines.leave.info),
    )


@router.post("/leave", status_code=status.HTTP_201_CREATED)
def request_leave(c: CtxDep, _: Physician, body: LeaveIn) -> LeaveOut:
    """M5: request leave without a trade ("Ohne Tausch beantragen"); the Planner decides."""
    if body.with_trade:
        raise EngineNotImplementedError(c.engines.optimizer.info)
    if body.end_date < body.start_date or body.start_date <= c.clock.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose future dates, start before end"
        )
    r = requests.create_leave(
        c.session, _staff_id(c), body.start_date, body.end_date, c.clock.now()
    )
    record(
        c,
        "leave.requested",
        "leave_request",
        r.id,
        r.staff_id,
        {"start_date": r.start_date.isoformat(), "end_date": r.end_date.isoformat()},
    )
    return _leave_out(r)


# --- M6 Dienst tauschen / Swap ----------------------------------------------------------------


class SwapOut(BaseModel):
    """A swap the person offered or took."""

    id: str
    shift: ShiftOut | None
    role: Literal["offered", "taken"]
    status: str
    escalation_reason: str | None
    decision_reason: str | None
    offered_at: datetime


class SwapAudience(BaseModel):
    """M6: how many colleagues the offer reaches (a count, never names)."""

    assignment_id: str
    eligible_colleagues: int
    check: str = CHECK


class SwapOfferIn(BaseModel):
    """Which own shift to offer."""

    assignment_id: str


class OpenOffer(BaseModel):
    """An open offer the person could take."""

    swap_id: str
    shift: ShiftOut
    offered_at: datetime
    check: str = CHECK


def _my_future_shift(c: Ctx, assignment_id: str) -> Shift:
    a = planning.assignment(c.session, assignment_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    s = next(
        (x for x in effective(c.session, a.day, a.day) if x.assignment_id == assignment_id), None
    )
    if s is None or s.holder != _staff_id(c):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your shift")
    if s.day <= c.clock.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Only future shifts can be offered"
        )
    return s


def _swap_out(c: Ctx, s: operations.Swap, me: str) -> SwapOut:
    a = planning.assignment(c.session, s.assignment_id)
    shift = (
        None
        if a is None
        else _shift_out(c, Shift(a.id, a.day, a.shift_type, None, a.staff_id, "planned"))
    )
    return SwapOut(
        id=s.id,
        shift=shift,
        role="offered" if s.offered_by == me else "taken",
        status=s.status,
        escalation_reason=s.escalation_reason,
        decision_reason=s.decision_reason,
        offered_at=s.offered_at,
    )


@router.get("/swaps")
def my_swaps(c: CtxDep, _: Physician) -> list[SwapOut]:
    """M6: swaps the person offered or took."""
    me = _staff_id(c)
    return [_swap_out(c, s, me) for s in operations.swaps(c.session, staff_id=me)[:50]]


@router.get("/swaps/audience")
def swap_audience(c: CtxDep, _: Physician, assignment_id: str) -> SwapAudience:
    """M6: how many colleagues could take this shift (basic filter, not checked against rules)."""
    s = _my_future_shift(c, assignment_id)
    n = len(basic_candidates(c, department(c), s, exclude={_staff_id(c)}))
    return SwapAudience(assignment_id=assignment_id, eligible_colleagues=n)


@router.post("/swaps", status_code=status.HTTP_201_CREATED)
def offer_swap(c: CtxDep, _: Physician, body: SwapOfferIn) -> SwapOut:
    """M6: offer an own future shift to eligible colleagues."""
    s = _my_future_shift(c, body.assignment_id)
    if any(
        x.status == "open"
        for x in operations.swaps(c.session, statuses=["open"])
        if x.assignment_id == s.assignment_id
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "This shift is already offered")
    sw = operations.offer_swap(c.session, s.assignment_id, _staff_id(c), c.clock.now())
    record(
        c,
        "swap.offered",
        "swap_offer",
        sw.id,
        sw.offered_by,
        {"date": s.day.isoformat(), "shift_type": s.shift_type},
    )
    return _swap_out(c, sw, _staff_id(c))


@router.get("/swap-offers")
def open_offers(c: CtxDep, _: Physician) -> list[OpenOffer]:
    """M6: open offers of colleagues the person could take (basic filter)."""
    me, dep = _staff_id(c), department(c)
    out = []
    for sw in operations.swaps(c.session, statuses=["open"]):
        if sw.offered_by == me or sw.offered_by not in dep.staff:
            continue
        a = planning.assignment(c.session, sw.assignment_id)
        if a is None or a.day <= c.clock.today():
            continue
        s = Shift(a.id, a.day, a.shift_type, sw.offered_by, a.staff_id, "planned")
        if any(p.id == me for p in basic_candidates(c, dep, s, exclude={sw.offered_by})):
            out.append(OpenOffer(swap_id=sw.id, shift=_shift_out(c, s), offered_at=sw.offered_at))
    return out


@router.post("/swap-offers/{swap_id}/take")
def take_offer(c: CtxDep, _: Physician, swap_id: str) -> SwapOut:
    """M6: take a colleague's offer. Without the validator (C2) the Planner decides."""
    me, dep = _staff_id(c), department(c)
    sw = operations.swap(c.session, swap_id)
    if sw is None or sw.offered_by not in dep.staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    a = planning.assignment(c.session, sw.assignment_id)
    assert a is not None
    s = Shift(a.id, a.day, a.shift_type, sw.offered_by, a.staff_id, "planned")
    if not any(p.id == me for p in basic_candidates(c, dep, s, exclude={sw.offered_by})):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot take this shift")
    try:
        taken = operations.take_swap(c.session, swap_id, me, c.clock.now())
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    record(
        c, "swap.taken", "swap_offer", swap_id, me, {"escalation_reason": taken.escalation_reason}
    )
    return _swap_out(c, taken, me)


# --- M7 Krank melden / Report sick ------------------------------------------------------------


class SickIn(BaseModel):
    """Dates only. There is no field for a diagnosis or a reason."""

    start_date: date | None = None
    end_date: date | None = None


class SickOut(BaseModel):
    """M7: the absence and the cover searches started."""

    start_date: date
    end_date: date
    status: str = "absent"
    affected_shifts: list[ShiftOut]
    cover_searches_started: int


@router.post("/sick", status_code=status.HTTP_201_CREATED)
def report_sick(c: CtxDep, _: Physician, body: SickIn) -> SickOut:
    """M7: report sick (no approval, PROCESS §2); cover searches start for each affected shift."""
    me, dep = _staff_id(c), department(c)
    start = body.start_date or c.clock.today()
    end = body.end_date or start
    if start < c.clock.today() or end < start or (end - start).days > 42:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose today or later, up to six weeks"
        )
    affected = [s for s in effective(c.session, start, end) if s.holder == me]
    absence = operations.report_absence(c.session, me, start, end, c.clock.now())
    record(
        c,
        "absence.reported",
        "absence",
        absence.id,
        me,
        {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "category": absence.category,
        },
    )
    opened = open_cascades_for(c, dep, me, absence.id, start, end)
    for cid in opened:
        record(c, "cover.search_started", "cover_cascade", cid, me)
    return SickOut(
        start_date=start,
        end_date=end,
        affected_shifts=[_shift_out(c, s) for s in affected],
        cover_searches_started=len(opened),
    )


# --- M8 Vertretungsanfrage / Cover request ----------------------------------------------------


class HoursImpact(BaseModel):
    """What taking the shift does to the person's month."""

    contract_hours: float
    planned_hours_before: float
    planned_hours_after: float


class CoverRequestOut(BaseModel):
    """M8: an open cover request to the person."""

    offer_id: str
    shift: ShiftOut
    deadline_at: datetime | None
    seconds_left: int | None
    hours: HoursImpact
    check: str = CHECK


class RespondIn(BaseModel):
    """Take the shift or decline."""

    accept: bool


class RespondOut(BaseModel):
    """What happens next."""

    status: str
    escalation_reason: str | None


@router.get("/cover-requests")
def cover_requests(c: CtxDep, _: Physician) -> list[CoverRequestOut]:
    """M8: open cover requests with countdown and hours impact."""
    me, dep = _staff_id(c), department(c)
    now = c.clock.now()
    out = []
    for task in _cover_tasks(c):
        m = month_start(task.shift.date)
        shifts = effective(c.session, m, month_end(m))
        leave = approved_leave_days(c.session, [me], m, month_end(m)).get(me, set())
        holidays = set(organization.holidays(c.session, m, month_end(m)))
        rules = organization.rules_for(c.session, m).rules
        h = hours_for(
            dep.staff[me],
            m,
            shifts,
            leave,
            holidays,
            rules,
            organization.shift_types(c.session),
            now,
        )
        add = credit(task.shift.shift_type, rules)
        left = (
            None
            if task.deadline_at is None
            else max(0, int((task.deadline_at - now).total_seconds()))
        )
        out.append(
            CoverRequestOut(
                offer_id=task.offer_id,
                shift=task.shift,
                deadline_at=task.deadline_at,
                seconds_left=left,
                hours=HoursImpact(
                    contract_hours=h.contract_hours,
                    planned_hours_before=h.planned_hours,
                    planned_hours_after=round(h.planned_hours + add, 2),
                ),
            )
        )
    return out


@router.post("/cover-requests/{offer_id}")
def respond_cover(c: CtxDep, _: Physician, offer_id: str, body: RespondIn) -> RespondOut:
    """M8: take the shift ("Übernehmen") or decline. Taking it waits for the Planner until C2."""
    me = _staff_id(c)
    operations.advance(c.session, c.clock.now())
    try:
        cas = operations.respond(c.session, offer_id, me, body.accept, c.clock.now())
    except KeyError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from e
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    record(c, "cover.accepted" if body.accept else "cover.declined", "cover_cascade", cas.id, me)
    return RespondOut(status=cas.status, escalation_reason=cas.escalation_reason)


# --- M9 Fairness-Bilanz -----------------------------------------------------------------------


class FairnessCategory(BaseModel):
    """The person's count against anonymous department statistics."""

    metric: str  # nights | weekends | holidays
    mine: int
    department_mean: float
    department_median: float
    department_min: int
    department_max: int
    distribution: list[int] = Field(description="All values, sorted, without names")


class MyFairness(BaseModel):
    """M9: nights, weekends and holidays this year."""

    year: int
    as_of: date
    categories: list[FairnessCategory]


def year_burden(c: Ctx, year: int) -> tuple[dict[str, fairness.Burden], list[str], date]:
    """Return burden per person for the year so far, and who counts as department."""
    dep = department(c)
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), c.clock.today())
    shifts = [s for s in effective(c.session, start, end) if s.holder]
    holidays = set(organization.holidays(c.session, start, end))
    counts = fairness.burden(
        ((s.holder, s.day, s.shift_type) for s in shifts if s.holder), holidays
    )
    people = [
        p.id
        for p in dep.staff.values()
        # Specialists and residents share the night and on-call rota; seniors do not.
        if p.role_on(end) in ("facharzt", "assistenzarzt") and p.rostered_on(end)
    ]
    return counts, people, end


@router.get("/fairness")
def my_fairness(c: CtxDep, _: Physician, year: int | None = None) -> MyFairness:
    """M9: own nights, weekends and holidays against the department (anonymous statistics)."""
    y = year or c.clock.today().year
    counts, people, as_of = year_burden(c, y)
    me = _staff_id(c)
    cats = []
    for cat in fairness.CATEGORIES:
        dist = fairness.distribution(counts, people, cat)
        cats.append(
            FairnessCategory(
                metric=cat,
                mine=counts.get(me, fairness.Burden()).get(cat),
                department_mean=dist.mean,
                department_median=dist.median,
                department_min=dist.minimum,
                department_max=dist.maximum,
                distribution=list(dist.values),
            )
        )
    return MyFairness(year=y, as_of=as_of, categories=cats)


# --- M10 Stunden / Hours ----------------------------------------------------------------------


class HoursOut(BaseModel):
    """M10: contract, planned, worked and overtime hours of a month."""

    roster_month: date
    contract_hours: float
    leave_credit_hours: float
    planned_hours: float
    worked_hours: float
    overtime_hours: float
    rest_compliance: None = Field(None, description="Needs the validator C2 (Phase 7)")
    rest_compliance_available_from_phase: int = 7


def hours_table(c: Ctx, m: date, staff_ids: list[str]) -> dict[str, HoursOut]:
    """Return the hours of several physicians in a month, computing the month once."""
    dep = department(c)
    shifts = effective(c.session, m, month_end(m))
    leave = approved_leave_days(c.session, staff_ids, m, month_end(m))
    holidays = set(organization.holidays(c.session, m, month_end(m)))
    rules = organization.rules_for(c.session, m).rules
    types = organization.shift_types(c.session)
    out = {}
    for sid in staff_ids:
        h = hours_for(
            dep.staff[sid], m, shifts, leave.get(sid, set()), holidays, rules, types, c.clock.now()
        )
        out[sid] = HoursOut(
            roster_month=m,
            contract_hours=h.contract_hours,
            leave_credit_hours=h.leave_credit,
            planned_hours=h.planned_hours,
            worked_hours=h.worked_hours,
            overtime_hours=h.overtime_hours,
        )
    return out


def hours_out(c: Ctx, staff_id: str, m: date) -> HoursOut:
    """Return the hours of one physician in a month."""
    return hours_table(c, m, [staff_id])[staff_id]


@router.get("/hours")
def my_hours(
    c: CtxDep, _: Physician, month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None
) -> HoursOut:
    """M10: own hours for a month (default: the current month)."""
    return hours_out(c, _staff_id(c), parse_month(month) if month else month_start(c.clock.today()))


# --- M11 Mitteilungen / Notifications --------------------------------------------------------


class Notification(BaseModel):
    """One notification (the app renders the text from ``kind`` and ``data``)."""

    kind: str
    at: datetime
    data: dict[str, str | None]


@router.get("/notifications")
def notifications(c: CtxDep, _: Physician) -> list[Notification]:
    """M11: roster published, swap updates, leave decisions, cover requests."""
    me, now = _staff_id(c), c.clock.now()
    out: list[Notification] = []
    for m in planning.published_months(c.session)[-3:]:
        pub = planning.published(c.session, m)
        if pub and pub.published_at and pub.published_at <= now:
            out.append(
                Notification(
                    kind="roster_published",
                    at=pub.published_at,
                    data={"roster_month": m.isoformat()},
                )
            )
    for r in requests.leave_requests(c.session, [me]):
        if r.decided_at and r.decided_at <= now:
            out.append(
                Notification(
                    kind=f"leave_{r.status}",
                    at=r.decided_at,
                    data={
                        "start_date": r.start_date.isoformat(),
                        "end_date": r.end_date.isoformat(),
                        "reason": r.decision_reason,
                    },
                )
            )
    for s in operations.swaps(c.session, staff_id=me):
        at = s.decided_at or s.accepted_at
        if (
            at
            and at <= now
            and s.status in ("approved", "declined", "accepted", "pending_approval")
        ):
            out.append(Notification(kind=f"swap_{s.status}", at=at, data={"swap_id": s.id}))
    for task in _cover_tasks(c):
        out.append(
            Notification(
                kind="cover_request",
                at=now,
                data={
                    "offer_id": task.offer_id,
                    "date": task.shift.date.isoformat(),
                    "shift_type": task.shift.shift_type,
                },
            )
        )
    return sorted(out, key=lambda n: n.at, reverse=True)[:30]


# --- M12 Einstellungen / Settings -------------------------------------------------------------


class SettingsOut(BaseModel):
    """M12: personal settings."""

    language: Literal["de", "en"]
    theme: Literal["auto", "light", "dark"]
    notifications: bool
    calendar_sync: bool
    preference_suggestions: bool


class SettingsIn(BaseModel):
    """Changes to personal settings."""

    language: Literal["de", "en"] | None = None
    theme: Literal["auto", "light", "dark"] | None = None
    notifications: bool | None = None
    calendar_sync: bool | None = None
    preference_suggestions: bool | None = None


@router.get("/settings")
def get_settings(c: CtxDep) -> SettingsOut:
    """M12: personal settings (every signed-in user)."""
    return SettingsOut(**identity.get_settings(c.session, c.user.id))


@router.put("/settings")
def put_settings(c: CtxDep, body: SettingsIn) -> SettingsOut:
    """M12: change personal settings. Oversight is read-only and cannot change anything."""
    if c.user.role == "oversight":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Oversight is read-only")
    return SettingsOut(**identity.update_settings(c.session, c.user.id, body.model_dump()))
