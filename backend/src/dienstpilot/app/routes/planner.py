"""Planner dashboard (W1–W8, W7b) and the department roster (Staff+ and Planner).

Only the Planner decides. The optimizer (C1) proposes variants in a background run; the
validator (C2) checks every edit, every candidate list and every variant before it is published.
Swaps and cover that C2 finds valid are approved by the Planner's policy; the rest waits here.
"""

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from dienstpilot.app.common import (
    Department,
    EngineLabel,
    department,
    in_department,
    label,
    record,
    settle_timers,
)
from dienstpilot.app.context import CtxDep
from dienstpilot.app.cover import CHECK, change_violations, ranked, valid_takers
from dienstpilot.app.deps import Ctx, OversightReaderDep, PlannerDep, RosterReaderDep
from dienstpilot.app.engine_inputs import Inputs
from dienstpilot.app.leave_hint import facts_for
from dienstpilot.app.privacy import absence_for
from dienstpilot.app.queue import QueueDep
from dienstpilot.app.roster import (
    Shift,
    approved_leave_days,
    credit,
    effective,
    hours_for,
    month_end,
    month_start,
    parse_month,
)
from dienstpilot.app.routes.me import HoursOut, hours_table, year_burden
from dienstpilot.fairness import service as fairness
from dienstpilot.identity.service import UserView
from dienstpilot.operations import service as operations
from dienstpilot.organization import service as organization
from dienstpilot.planning import service as planning
from dienstpilot.requests import service as requests
from dienstpilot.shared.ports import ForecastContext
from dienstpilot.workflows import reminders
from dienstpilot.workflows.reminders import window_recipients
from dienstpilot_validator import Assignment, Violation

router = APIRouter(tags=["planner dashboard"])
Month = Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]


# --- department roster (W4 grid; Staff+ read) -------------------------------------------------


class Cell(BaseModel):
    """What a physician has on a day."""

    shifts: list[str]
    assignment_ids: list[str] = Field(description="Same order as shifts (W4 edits)")
    changed: bool
    on_leave: bool
    absence: dict[str, str] | None = Field(
        None, description="status 'absent'; the category only for the Planner"
    )
    wish: Literal["granted", "missed"] | None = None


class RosterRow(BaseModel):
    """A physician's month."""

    staff_id: str
    display_name: str
    title_de: str
    title_en: str
    cells: dict[str, Cell]


class CoverageRow(BaseModel):
    """Demand against assigned physicians for one day, shift and qualification."""

    date: date
    shift_type: str
    qualification: str
    required: int
    assigned: int


class GapSuggestion(BaseModel):
    """Who could fill a gap (Planner only; checked by C2, ranked by C5)."""

    date: date
    shift_type: str
    candidates: list[str]
    check: str = CHECK
    engine: EngineLabel


class RosterGrid(BaseModel):
    """W4: the department's month."""

    roster_month: date
    status: Literal["published", "draft", "not_planned"]
    published_at: datetime | None
    rule_set_version: str | None
    rows: list[RosterRow]
    coverage: list[CoverageRow]
    gaps: list[GapSuggestion]


@router.get("/roster")
def roster(
    c: CtxDep, user: RosterReaderDep, month: Month, variant_id: str | None = None
) -> RosterGrid:
    """W4 grid and the full roster for Staff+: shifts, absences, leave, coverage per shift.

    With ``variant_id`` (Planner only) the grid shows a draft variant of a C1 run.
    """
    m = parse_month(month)
    dep = department(c)
    end = month_end(m)
    if variant_id is not None:
        if user.role != "planner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Drafts are for the Planner")
        try:
            info = planning.variant(c.session, variant_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from e
        if info is None or info[1] != m:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        draft = [
            Shift(a.id, a.day, a.shift_type, a.staff_id, a.staff_id, "planned")
            for a in planning.variant_assignments(c.session, variant_id)
        ]
        return _grid(
            c, user, dep, m, draft, "draft", None, organization.rules_for(c.session, m).version
        )
    pub = planning.published(c.session, m)
    if pub is None or (
        pub.published_at and pub.published_at > c.clock.now() and user.role != "planner"
    ):
        return RosterGrid(
            roster_month=m,
            status="not_planned",
            published_at=None,
            rule_set_version=None,
            rows=[],
            coverage=[],
            gaps=[],
        )
    return _grid(
        c,
        user,
        dep,
        m,
        effective(c.session, m, end),
        "published",
        pub.published_at,
        pub.rule_set_version,
    )


def _grid(
    c: Ctx,
    user: UserView,
    dep: Department,
    m: date,
    shifts: list[Shift],
    kind: Literal["published", "draft"],
    published_at: datetime | None,
    rule_set_version: str,
) -> RosterGrid:
    end = month_end(m)
    ids = list(dep.staff)
    leave = approved_leave_days(c.session, ids, m, end)
    absences = operations.absences(c.session, ids, m, end)
    window = requests.window_for(c.session, m)
    wishes = requests.preferences(c.session, window.id) if window and user.role == "planner" else []
    rows = []
    for p in sorted(dep.staff.values(), key=lambda s: s.display_name):
        if not any(p.rostered_on(m + timedelta(days=i)) for i in range((end - m).days + 1)):
            continue
        contract = p.contract_on(end) or p.contract_on(m)
        cells: dict[str, Cell] = {}
        d = m
        while d <= end:
            mine = [s for s in shifts if s.day == d and s.holder == p.id]
            ab = next(
                (a for a in absences if a.staff_id == p.id and a.start_date <= d <= a.end_date),
                None,
            )
            mark: Literal["granted", "missed"] | None = None
            for w in wishes:
                if w.staff_id == p.id and w.day == d and w.kind == "wish_work":
                    mark = (
                        "granted"
                        if any(w.shift_type in (None, s.shift_type) for s in mine)
                        else "missed"
                    )
            if mine or ab or d in leave.get(p.id, set()) or mark:
                cells[d.isoformat()] = Cell(
                    shifts=[s.shift_type for s in mine],
                    assignment_ids=[s.assignment_id for s in mine],
                    changed=any(s.note != "planned" for s in mine),
                    on_leave=d in leave.get(p.id, set()),
                    absence=None if ab is None else absence_for(user, ab.category),
                    wish=mark,
                )
            d += timedelta(days=1)
        rows.append(
            RosterRow(
                staff_id=p.id,
                display_name=p.display_name,
                title_de=contract.title_de if contract else "",
                title_en=contract.title_en if contract else "",
                cells=cells,
            )
        )
    coverage, gaps = [], []
    inputs = Inputs(c.session, dep, c.clock.now())
    for d, demand_rows in sorted(organization.demand(c.session, m, end).items()):
        for shift_type, qual, required in demand_rows:
            holders = [
                s.holder for s in shifts if s.day == d and s.shift_type == shift_type and s.holder
            ]
            have = (
                len(holders)
                if qual == "any"
                else sum(dep.staff[h].qualified(qual, d) for h in holders if h in dep.staff)
            )
            coverage.append(
                CoverageRow(
                    date=d,
                    shift_type=shift_type,
                    qualification=qual,
                    required=required,
                    assigned=have,
                )
            )
            if (
                have < required
                and user.role == "planner"
                and kind == "published"
                and d > c.clock.today()
            ):
                probe = Shift("", d, shift_type, None, "", "open")
                people = valid_takers(c, dep, probe, exclude=set(), inputs=inputs)
                top = [
                    dep.staff[x.staff_id].display_name
                    for x in ranked(c, dep, people, d, shift_type)[:3]
                ]
                gaps.append(
                    GapSuggestion(
                        date=d,
                        shift_type=shift_type,
                        candidates=top,
                        engine=label(c.engines.cover_ranker.info),
                    )
                )
    return RosterGrid(
        roster_month=m,
        status=kind,
        published_at=published_at,
        rule_set_version=rule_set_version,
        rows=rows,
        coverage=coverage,
        gaps=gaps,
    )


class ViolationOut(BaseModel):
    """A broken rule, as i18n keys with parameters (packages/i18n: violation.*, fix.*)."""

    rule: str
    key: str
    staff_id: str | None
    display_name: str | None
    date: date
    params: dict[str, Any]
    fix_key: str
    fix_params: dict[str, Any]


def violations_out(dep: Department, vs: list[Violation]) -> list[ViolationOut]:
    """Return violations for the API (names resolved here, in the UI layer)."""
    return [
        ViolationOut(
            rule=v.rule,
            key=v.key,
            staff_id=v.staff_id,
            display_name=dep.name(v.staff_id),
            date=v.day,
            params=v.params,
            fix_key=v.fix_key,
            fix_params=v.fix_params,
        )
        for v in sorted(vs, key=lambda v: (v.day, v.key, v.staff_id or ""))
    ]


def _unprocessable(dep: Department, message: str, vs: list[Violation]) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        {
            "code": "rule_violation",
            "message": message,
            "violations": [v.model_dump(mode="json") for v in violations_out(dep, vs)],
        },
    )


class AddShift(BaseModel):
    """A shift to add."""

    date: date
    shift_type: str
    staff_id: str


class AssignmentEdit(BaseModel):
    """W4: one change. A draft changes directly; a published roster needs a reason.

    ``assignment_id`` with ``new_staff_id`` reassigns (``null`` removes the shift); ``add``
    adds a shift. A change to a published roster must not break any rule (C2), and everyone
    affected is notified.
    """

    variant_id: str | None = Field(
        None, description="A draft variant; omit for the published roster"
    )
    assignment_id: str | None = None
    new_staff_id: str | None = None
    add: AddShift | None = None
    reason: str | None = Field(None, max_length=500)


class EditOut(BaseModel):
    """What the change did, and the violations of the changed people and days."""

    roster_month: date
    change_id: str | None
    notified: list[str]
    introduced: list[ViolationOut]
    violations: list[ViolationOut]
    validator: EngineLabel


@router.patch("/planner/roster/assignments")
def change_assignment(c: CtxDep, _: PlannerDep, body: AssignmentEdit) -> EditOut:
    """W4: change a draft (live validation) or a published roster (reason, C2-valid, notify)."""
    dep = department(c)
    if (body.assignment_id is None) == (body.add is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Give either assignment_id or add"
        )
    for sid in (body.new_staff_id, body.add.staff_id if body.add else None):
        if sid is not None:
            in_department(dep, sid)
    inputs = Inputs(c.session, dep, c.clock.now())
    if body.variant_id is not None:
        return _edit_draft(c, dep, inputs, body)
    if not (body.reason and body.reason.strip()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A change to a published roster needs a reason"
        )
    remove: list[Assignment] = []
    add: list[Assignment] = []
    before: str | None
    after: str | None
    if body.add is not None:
        day, shift_type, before, after = body.add.date, body.add.shift_type, None, body.add.staff_id
        kind = "add"
    else:
        assert body.assignment_id is not None
        a = planning.assignment(c.session, body.assignment_id)
        current = (
            None
            if a is None
            else next(
                (x for x in effective(c.session, a.day, a.day) if x.assignment_id == a.id), None
            )
        )
        if a is None or current is None or a.staff_id not in dep.staff:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        day, shift_type, before, after = a.day, a.shift_type, current.holder, body.new_staff_id
        kind = "remove" if after is None else "reassign"
        if before == after:
            raise HTTPException(status.HTTP_409_CONFLICT, "Nothing changes")
    m = month_start(day)
    if planning.published(c.session, m) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This month is not published")
    if day <= c.clock.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only future days can change")
    if before:
        remove.append(Assignment(before, day, shift_type))
    if after:
        add.append(Assignment(after, day, shift_type))
    people = {x for x in (before, after) if x}
    introduced = change_violations(c, inputs, remove, add, people)
    if introduced:
        raise _unprocessable(dep, "The change breaks a rule", introduced)
    assert c.user.staff_id is not None
    ch = planning.record_change(
        c.session,
        month=m,
        kind=kind,
        assignment_id=body.assignment_id,
        day=day,
        shift_type=shift_type,
        staff_before=before,
        staff_after=after,
        reason=body.reason.strip(),
        changed_by=c.user.staff_id,
        now=c.clock.now(),
    )
    notified = sorted(people)
    for sid in notified:
        record(
            c,
            "roster.changed",
            "assignment_change",
            ch.id,
            sid,
            {
                "date": day.isoformat(),
                "shift_type": shift_type,
                "kind": kind,
                "staff_before": before,
                "staff_after": after,
                "reason": ch.reason,
            },
        )
    after_inp = Inputs(c.session, dep, c.clock.now()).month(m)
    return EditOut(
        roster_month=m,
        change_id=ch.id,
        notified=notified,
        introduced=[],
        violations=violations_out(
            dep, [v for v in c.engines.validator.validate(after_inp) if v.staff_id in people]
        ),
        validator=label(c.engines.validator.info),
    )


def _edit_draft(c: Ctx, dep: Department, inputs: Inputs, body: AssignmentEdit) -> EditOut:
    assert body.variant_id is not None
    info = planning.variant(c.session, body.variant_id)
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    v, m = info
    if v.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft changes directly")
    own = {a.id: a for a in planning.variant_assignments(c.session, body.variant_id)}
    if body.add is not None:
        if month_start(body.add.date) != m:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "The day is not in this month"
            )
        remove: list[Assignment] = []
        add = [Assignment(body.add.staff_id, body.add.date, body.add.shift_type)]
    else:
        a = own.get(body.assignment_id or "")
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        remove = [Assignment(a.staff_id, a.day, a.shift_type)]
        add = [Assignment(body.new_staff_id, a.day, a.shift_type)] if body.new_staff_id else []
    inp = inputs.variant(body.variant_id)
    after, introduced = c.engines.validator.validate_change(inp, remove, add)
    planning.edit_draft(
        c.session,
        body.variant_id,
        [(x.staff_id, x.day, x.shift_type) for x in remove],
        [(x.staff_id, x.day, x.shift_type) for x in add],
    )
    return EditOut(
        roster_month=m,
        change_id=None,
        notified=[],
        introduced=violations_out(dep, introduced),
        violations=violations_out(dep, after),
        validator=label(c.engines.validator.info),
    )


class ValidateIn(BaseModel):
    """A month to validate: the published roster as it stands, or a draft variant."""

    roster_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    variant_id: str | None = None


class ValidationOut(BaseModel):
    """W4: every violation of the month."""

    roster_month: date
    variant_id: str | None
    valid: bool
    by_rule: dict[str, int]
    violations: list[ViolationOut]
    validator: EngineLabel


@router.post("/planner/validate")
def validate(c: CtxDep, _: PlannerDep, body: ValidateIn) -> ValidationOut:
    """W4: live validation with C2 (all rules, the whole month)."""
    dep = department(c)
    m = parse_month(body.roster_month)
    inputs = Inputs(c.session, dep, c.clock.now())
    if body.variant_id is not None:
        info = planning.variant(c.session, body.variant_id)
        if info is None or info[1] != m:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        inp = inputs.variant(body.variant_id)
    elif planning.published(c.session, m) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This month has no roster yet")
    else:
        inp = inputs.month(m)
    vs = c.engines.validator.validate(inp)
    by_rule: dict[str, int] = {}
    for v in vs:
        by_rule[v.rule] = by_rule.get(v.rule, 0) + 1
    return ValidationOut(
        roster_month=m,
        variant_id=body.variant_id,
        valid=not vs,
        by_rule=by_rule,
        violations=violations_out(dep, vs),
        validator=label(c.engines.validator.info),
    )


# --- W3 Varianten, W5 Freigabe ----------------------------------------------------------------


class VariantOut(BaseModel):
    """A variant and what it achieves (metrics from C1, checked by C2)."""

    variant_id: str
    label: str
    status: Literal["published", "draft", "discarded"]
    profile: str | None
    recommended: bool
    recommendation_key: str | None = Field(
        None, description="i18n key of the reason (deterministic: the balanced profile)"
    )
    metrics: dict[str, Any] | None
    published_at: datetime | None


class RunOut(BaseModel):
    """A roster run of a month and the versions behind it."""

    run_id: str
    status: Literal["queued", "running", "done", "infeasible", "failed"]
    planner_kind: str
    rule_set_version: str
    generator_version: str | None
    solver_version: str | None
    validator_version: str | None
    created_at: datetime
    finished_at: datetime | None
    config: dict[str, Any] | None
    explanations: list[dict[str, Any]]
    error: str | None
    trial: bool
    variants: list[VariantOut]


class RunsOut(BaseModel):
    """W3: runs and variants of a month."""

    roster_month: date
    runs: list[RunOut]
    optimizer: EngineLabel


def _is_trial(c: Ctx, month: date) -> bool:
    """Tell whether the request window of a month is open, so its runs are trial runs."""
    w = requests.window_for(c.session, month)
    return w is not None and w.status == "open"


def _run_out(r: planning.Run, kind: str, generator: str | None, trial: bool) -> RunOut:
    return RunOut(
        run_id=r.id,
        status=r.status,
        planner_kind=kind,
        rule_set_version=r.rule_set_version,
        generator_version=generator,
        solver_version=r.solver_version,
        validator_version=r.validator_version,
        created_at=r.created_at,
        finished_at=r.finished_at,
        config=r.config,
        explanations=r.explanations or [],
        error=r.error,
        trial=trial,
        variants=[
            VariantOut(
                variant_id=v.id,
                label=v.label,
                status=v.status,
                profile=v.profile,
                recommended=v.recommended,
                recommendation_key="recommendation.balanced" if v.recommended else None,
                metrics=v.metrics,
                published_at=v.published_at,
            )
            for v in r.variants
        ],
    )


@router.get("/planner/runs")
def runs(c: CtxDep, _: PlannerDep, month: Month) -> RunsOut:
    """W3: every run of a month (the seeded manual roster and C1 runs), newest first."""
    m = parse_month(month)
    trial = _is_trial(c, m)
    kinds = {r.run_id: (r.planner_kind, r.generator_version) for r in planning.runs(c.session, m)}
    return RunsOut(
        roster_month=m,
        optimizer=label(c.engines.optimizer.info),
        runs=[
            _run_out(r, *kinds.get(r.id, ("c1", None)), trial)
            for r in planning.runs_of(c.session, m)
        ],
    )


class RunIn(BaseModel):
    """Generate variants for a month."""

    roster_month: str = Field(pattern=r"^\d{4}-\d{2}$")


class RunQueued(BaseModel):
    """The run is queued; poll ``GET /planner/runs/{run_id}``."""

    run_id: str
    status: str


@router.post("/planner/runs", status_code=status.HTTP_202_ACCEPTED)
def generate(c: CtxDep, _: PlannerDep, queue: QueueDep, body: RunIn) -> RunQueued:
    """W3: queue a C1 run for a month that is not published yet; the worker solves it."""
    m = parse_month(body.roster_month)
    if m <= month_start(c.clock.today()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Plan a future month")
    if planning.published(c.session, m) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This month is already published")
    if any(r.status in ("queued", "running") for r in planning.runs_of(c.session, m)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A run for this month is in progress")
    assert c.user.staff_id is not None
    rule_set = organization.rules_for(c.session, m)
    run_id = planning.create_run(c.session, m, rule_set.version, c.user.staff_id, c.clock.now())
    record(c, "run.requested", "roster_run", run_id, None, {"roster_month": m.isoformat()})
    c.session.commit()
    queue.enqueue("run_roster", run_id=run_id, department_id=c.user.department_id)
    return RunQueued(run_id=run_id, status="queued")


@router.get("/planner/runs/{run_id}")
def run_detail(c: CtxDep, _: PlannerDep, run_id: str) -> RunOut:
    """W3: a run's progress, its variants with metrics, or why no valid roster exists."""
    try:
        r = planning.run(c.session, run_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from e
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    kinds = {
        x.run_id: (x.planner_kind, x.generator_version)
        for x in planning.runs(c.session, r.roster_month)
    }
    return _run_out(r, *kinds.get(r.id, ("c1", None)), _is_trial(c, r.roster_month))


class Published(BaseModel):
    """W5: the published variant and its approval."""

    variant_id: str
    roster_month: date
    published_at: datetime
    approved_by: str
    validator: EngineLabel


@router.post("/planner/variants/{variant_id}/publish")
def publish(c: CtxDep, _: PlannerDep, variant_id: str) -> Published:
    """W5: approve and publish a draft. It must pass the validator (C2) without a violation."""
    dep = department(c)
    try:
        info = planning.variant(c.session, variant_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from e
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    v, m = info
    if planning.published(c.session, m) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This month is already published")
    if v.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft can be published")
    if _is_trial(c, m):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The request window is still open: close it before publishing",
        )
    vs = c.engines.validator.validate(Inputs(c.session, dep, c.clock.now()).variant(variant_id))
    if vs:
        raise _unprocessable(dep, "The variant breaks a rule", vs)
    assert c.user.staff_id is not None
    now = c.clock.now()
    planning.publish_variant(c.session, variant_id, c.user.staff_id, now)
    record(
        c,
        "roster.published",
        "roster_variant",
        variant_id,
        None,
        {
            "roster_month": m.isoformat(),
            "label": v.label,
            "profile": v.profile,
            "validator_version": c.engines.validator.info.version,
        },
    )
    return Published(
        variant_id=variant_id,
        roster_month=m,
        published_at=now,
        approved_by=c.user.display_name,
        validator=label(c.engines.validator.info),
    )


class PolicyOut(BaseModel):
    """What the system approves on its own: only C2-valid swaps and cover inside the department.

    Cover by a locum or from another department, and cover that means overtime, always go to
    the Planner.
    """

    auto_approve_swaps: bool
    auto_approve_cover: bool
    updated_by: str | None
    updated_at: datetime | None


class PolicyIn(BaseModel):
    """Switch auto-approval on or off."""

    auto_approve_swaps: bool
    auto_approve_cover: bool


def _policy_out(dep: Department, p: operations.Policy) -> PolicyOut:
    return PolicyOut(
        auto_approve_swaps=p.auto_approve_swaps,
        auto_approve_cover=p.auto_approve_cover,
        updated_by=dep.name(p.updated_by),
        updated_at=p.updated_at,
    )


@router.get("/planner/policy")
def get_policy(c: CtxDep, _: PlannerDep) -> PolicyOut:
    """W11: the auto-approval policy."""
    dep = department(c)
    return _policy_out(dep, operations.policy(c.session, dep.id))


@router.put("/planner/policy")
def put_policy(c: CtxDep, _: PlannerDep, body: PolicyIn) -> PolicyOut:
    """W11: change the auto-approval policy (audited)."""
    dep = department(c)
    assert c.user.staff_id is not None
    p = operations.set_policy(
        c.session,
        dep.id,
        body.auto_approve_swaps,
        body.auto_approve_cover,
        c.user.staff_id,
        c.clock.now(),
    )
    record(c, "policy.changed", "policy", dep.id, None, body.model_dump())
    return _policy_out(dep, p)


# --- W1 Übersicht -----------------------------------------------------------------------------


class WindowProgress(BaseModel):
    """Progress of the open request window."""

    roster_month: date
    responded: int
    recipients: int
    closes_at: datetime
    days_left: int


class CoverageDay(BaseModel):
    """Coverage and expected absences of one day."""

    date: date
    short: int = Field(description="Demand rows with fewer physicians than required")
    expected_absences: float
    expected_low: float
    expected_high: float


class RecentChange(BaseModel):
    """A swap or cover settled recently."""

    kind: Literal["swap", "cover"]
    at: datetime
    date: date
    shift_type: str
    staff_name: str | None
    approval: str | None


class Overview(BaseModel):
    """W1: what needs the Planner today."""

    now: datetime
    published_month: date | None
    planning_month: date | None
    window: WindowProgress | None
    escalations: int
    pending_leave: int
    open_proposals: int
    coverage: list[CoverageDay]
    forecast_engine: EngineLabel
    recent: list[RecentChange]


def _window_progress(c: Ctx) -> WindowProgress | None:
    w = next((w for w in requests.windows(c.session) if w.status == "open"), None)
    if w is None:
        return None
    days_left = (w.closes_at.astimezone(c.clock.now().tzinfo).date() - c.clock.today()).days
    return WindowProgress(
        roster_month=w.roster_month,
        responded=len(requests.responses(c.session, w.id)),
        recipients=w.recipient_count,
        closes_at=w.closes_at,
        days_left=days_left,
    )


@router.get("/planner/overview")
def overview(c: CtxDep, _: PlannerDep) -> Overview:
    """W1: window progress, escalations, coverage of the next 14 days with expected absences."""
    now, today = c.clock.now(), c.clock.today()
    settle_timers(c)
    dep = department(c)
    days = [today + timedelta(days=i) for i in range(14)]
    shifts = effective(c.session, days[0], days[-1])
    demand = organization.demand(c.session, days[0], days[-1])
    history = [
        (a.start_date, a.end_date)
        for a in operations.absences(c.session, list(dep.staff), date(2021, 1, 1), today)
    ]
    night_shifts: dict[date, int] = {}
    for n in planning.assignments(c.session, today - timedelta(days=7), today):
        if n.shift_type == "nacht":
            night_shifts[n.day] = night_shifts.get(n.day, 0) + 1
    context = ForecastContext(
        as_of=today,  # the demo clock, never the system time
        night_shifts=night_shifts,
        holidays=frozenset(organization.holidays(c.session, days[0], days[-1])),
        school_holidays=organization.school_holiday_days(c.session, days[0], days[-1]),
    )
    forecast = {f.day: f for f in c.engines.forecaster.forecast(days, history, context)}
    coverage = []
    for d in days:
        short = 0
        for shift_type, qual, required in demand.get(d, []):
            holders = [
                s.holder for s in shifts if s.day == d and s.shift_type == shift_type and s.holder
            ]
            have = (
                len(holders)
                if qual == "any"
                else sum(dep.staff[h].qualified(qual, d) for h in holders if h in dep.staff)
            )
            short += have < required
        f = forecast[d]
        coverage.append(
            CoverageDay(
                date=d,
                short=short,
                expected_absences=f.expected,
                expected_low=f.low,
                expected_high=f.high,
            )
        )
    escalations = len(operations.swaps(c.session, statuses=["pending_approval"])) + len(
        operations.cascades(c.session, statuses=["pending_approval"])
    )
    pending_leave = len(requests.leave_requests(c.session, list(dep.staff), status="pending"))
    recent: list[RecentChange] = []
    since = now - timedelta(days=7)
    for s in operations.swaps(
        c.session, statuses=["accepted", "approved"], since=since - timedelta(days=30)
    ):
        at = s.decided_at or s.accepted_at
        a = planning.assignment(c.session, s.assignment_id)
        if at and since <= at <= now and a:
            recent.append(
                RecentChange(
                    kind="swap",
                    at=at,
                    date=a.day,
                    shift_type=a.shift_type,
                    staff_name=dep.name(s.accepted_by),
                    approval=s.approval,
                )
            )
    for cas in operations.cascades(c.session, statuses=["closed"], since=since):
        a = planning.assignment(c.session, cas.assignment_id)
        if a and cas.closed_at and cas.closed_at <= now:
            recent.append(
                RecentChange(
                    kind="cover",
                    at=cas.closed_at,
                    date=a.day,
                    shift_type=a.shift_type,
                    staff_name=dep.name(cas.covered_by),
                    approval=cas.approval or "planner",
                )
            )
    months = planning.published_months(c.session)
    published = [
        m
        for m in months
        if (p := planning.published(c.session, m)) and p.published_at and p.published_at <= now
    ]
    window = _window_progress(c)
    return Overview(
        now=now,
        published_month=published[-1] if published else None,
        planning_month=window.roster_month if window else None,
        window=window,
        escalations=escalations,
        pending_leave=pending_leave,
        open_proposals=len(planning.proposals(c.session, dep.id, "open")),
        coverage=coverage,
        forecast_engine=label(c.engines.forecaster.info),
        recent=sorted(recent, key=lambda r: r.at, reverse=True)[:10],
    )


# --- W2 Wunschphase ---------------------------------------------------------------------------


class Respondent(BaseModel):
    """Who received the window and whether they answered."""

    staff_id: str
    display_name: str
    responded_at: datetime | None


class WindowDetail(BaseModel):
    """W2: progress and the list of who has and hasn't answered."""

    roster_month: date
    status: str
    opens_at: datetime
    closes_at: datetime
    responded: int
    recipients: int
    people: list[Respondent]


def _window(c: Ctx, month: str) -> requests.Window:
    w = requests.window_for(c.session, parse_month(month))
    if w is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No window for this month")
    return w


@router.get("/planner/windows/{month}")
def window_detail(c: CtxDep, _: PlannerDep, month: str) -> WindowDetail:
    """W2: who has answered the window."""
    w, dep = _window(c, month), department(c)
    answered = requests.responses(c.session, w.id)
    people = [
        Respondent(staff_id=p.id, display_name=p.display_name, responded_at=answered.get(p.id))
        for p in window_recipients(w, dep.staff.values())
    ]
    people.sort(key=lambda r: (r.responded_at is not None, r.display_name))
    return WindowDetail(
        roster_month=w.roster_month,
        status=w.status,
        opens_at=w.opens_at,
        closes_at=w.closes_at,
        responded=len(answered),
        recipients=w.recipient_count,
        people=people,
    )


class ReminderOut(BaseModel):
    """How many were reminded."""

    reminded: int


@router.post("/planner/windows/{month}/reminders")
def remind(c: CtxDep, _: PlannerDep, month: str) -> ReminderOut:
    """W2: "Erinnerung senden" to everyone who has not answered (push comes later)."""
    d = window_detail(c, _, month)
    n = sum(1 for p in d.people if p.responded_at is None)
    record(
        c, "window.reminder_sent", "request_window", _window(c, month).id, payload={"reminded": n}
    )
    return ReminderOut(reminded=n)


@router.post("/planner/windows/{month}/close")
def close_window(c: CtxDep, _: PlannerDep, month: str) -> WindowDetail:
    """W2: close the window."""
    w = _window(c, month)
    if w.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "The window is not open")
    requests.set_window_status(c.session, w.id, "closed")
    reminders.closed(c.session, w.id, c.clock.now())
    record(c, "window.closed", "request_window", w.id)
    return window_detail(c, _, month)


# --- W6 Anfragen ------------------------------------------------------------------------------


class LeaveImpact(BaseModel):
    """What a leave request would mean."""

    hint: str
    max_on_leave_same_day: int
    limit: int
    leave_days_taken_this_year: int
    department_mean_leave_days: float
    engine: EngineLabel


class PendingLeave(BaseModel):
    """A leave request waiting for the Planner."""

    id: str
    staff_id: str
    display_name: str
    start_date: date
    end_date: date
    submitted_at: datetime
    impact: LeaveImpact


class PendingSwap(BaseModel):
    """A taken swap waiting for the Planner."""

    id: str
    date: date
    shift_type: str
    offered_by: str | None
    taken_by: str | None
    escalation_reason: str | None


class PendingCascade(BaseModel):
    """A cover search waiting for the Planner."""

    id: str
    date: date
    shift_type: str
    accepted_by: str | None
    escalation_reason: str | None


class ProposalOut(BaseModel):
    """A proposal in the inbox."""

    id: str
    source: str
    title: str
    body: str
    created_at: datetime
    roster_month: date | None
    status: str


class Inbox(BaseModel):
    """W6: everything waiting for the Planner."""

    leave: list[PendingLeave]
    swaps: list[PendingSwap]
    cascades: list[PendingCascade]
    proposals: list[ProposalOut]


@router.get("/planner/requests")
def inbox(c: CtxDep, _: PlannerDep) -> Inbox:
    """W6: pending leave with computed impact, escalated swaps and cover, open proposals."""
    dep = department(c)
    settle_timers(c)
    ids = list(dep.staff)
    year = c.clock.today().year
    taken = {
        sid: sum(1 for d in days if d.weekday() < 5)
        for sid, days in approved_leave_days(
            c.session, ids, date(year, 1, 1), date(year, 12, 31)
        ).items()
    }
    active = [p.id for p in dep.rostered(c.clock.today())]
    mean_taken = round(sum(taken.get(p, 0) for p in active) / len(active), 1) if active else 0.0
    leave = []
    for r in requests.leave_requests(c.session, ids, status="pending"):
        facts = facts_for(c.session, dep, r.staff_id, r.start_date, r.end_date, c.clock.today())
        h = c.engines.leave.hint(facts, 6)
        leave.append(
            PendingLeave(
                id=r.id,
                staff_id=r.staff_id,
                display_name=dep.name(r.staff_id) or "",
                start_date=r.start_date,
                end_date=r.end_date,
                submitted_at=r.submitted_at,
                impact=LeaveImpact(
                    hint=h.outcome,
                    max_on_leave_same_day=h.max_overlapping,
                    limit=h.limit,
                    leave_days_taken_this_year=taken.get(r.staff_id, 0),
                    department_mean_leave_days=mean_taken,
                    engine=label(c.engines.leave.info),
                ),
            )
        )
    swaps = []
    for s in operations.swaps(c.session, statuses=["pending_approval"]):
        a = planning.assignment(c.session, s.assignment_id)
        if a and s.offered_by in dep.staff:
            swaps.append(
                PendingSwap(
                    id=s.id,
                    date=a.day,
                    shift_type=a.shift_type,
                    offered_by=dep.name(s.offered_by),
                    taken_by=dep.name(s.accepted_by),
                    escalation_reason=s.escalation_reason,
                )
            )
    cascades = []
    for cas in operations.cascades(c.session, statuses=["pending_approval"]):
        a = planning.assignment(c.session, cas.assignment_id)
        if a and a.staff_id in dep.staff:
            cascades.append(
                PendingCascade(
                    id=cas.id,
                    date=a.day,
                    shift_type=a.shift_type,
                    accepted_by=dep.name(cas.covered_by),
                    escalation_reason=cas.escalation_reason,
                )
            )
    props = [
        ProposalOut(
            id=p.id,
            source=p.source,
            title=p.title,
            body=p.body,
            created_at=p.created_at,
            roster_month=p.roster_month,
            status=p.status,
        )
        for p in planning.proposals(c.session, dep.id, "open")
    ]
    return Inbox(leave=leave, swaps=swaps, cascades=cascades, proposals=props)


class Decision(BaseModel):
    """Approve or decline. A decline needs the Planner's reason (shown to the requester)."""

    approve: bool
    reason: str | None = Field(None, max_length=500)


class Decided(BaseModel):
    """The new state."""

    id: str
    status: str


@router.post("/planner/leave/{request_id}/decision")
def decide_leave(c: CtxDep, _: PlannerDep, request_id: str, body: Decision) -> Decided:
    """W6: "Genehmigen" or "Ablehnen mit Begründung"."""
    dep = department(c)
    r = requests.leave_request(c.session, request_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    in_department(dep, r.staff_id)
    if not body.approve and not (body.reason and body.reason.strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A decline needs a reason")
    try:
        r = requests.decide_leave(
            c.session, request_id, body.approve, c.user.staff_id, body.reason, c.clock.now()
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    record(
        c,
        f"leave.{r.status}",
        "leave_request",
        r.id,
        r.staff_id,
        {
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "decision_reason": r.decision_reason,
        },
    )
    return Decided(id=r.id, status=r.status)


@router.post("/planner/swaps/{swap_id}/decision")
def decide_swap(c: CtxDep, _: PlannerDep, swap_id: str, body: Decision) -> Decided:
    """W6: approve or decline an escalated swap. An approval must pass the validator (C2)."""
    dep = department(c)
    s = operations.swap(c.session, swap_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    in_department(dep, s.offered_by)
    assert c.user.staff_id is not None
    a = planning.assignment(c.session, s.assignment_id)
    if body.approve and a is not None and s.accepted_by:
        remove = [Assignment(s.offered_by, a.day, a.shift_type)]
        add = [Assignment(s.accepted_by, a.day, a.shift_type)]
        counter = (
            None
            if s.counter_assignment_id is None
            else planning.assignment(c.session, s.counter_assignment_id)
        )
        if counter is not None:
            remove.append(Assignment(s.accepted_by, counter.day, counter.shift_type))
            add.append(Assignment(s.offered_by, counter.day, counter.shift_type))
        introduced = change_violations(
            c,
            Inputs(c.session, dep, c.clock.now()),
            remove,
            add,
            {s.offered_by, s.accepted_by},
        )
        if introduced:
            raise _unprocessable(dep, "The swap breaks a rule", introduced)
    try:
        s = operations.decide_swap(
            c.session, swap_id, body.approve, c.user.staff_id, body.reason, c.clock.now()
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    record(
        c,
        f"swap.{s.status}",
        "swap_offer",
        s.id,
        s.accepted_by,
        {"decision_reason": s.decision_reason},
    )
    return Decided(id=s.id, status=s.status)


class ProposalDecision(BaseModel):
    """Accept (to act on it) or dismiss a proposal."""

    accept: bool


@router.post("/planner/proposals/{proposal_id}/decision")
def decide_proposal(c: CtxDep, _: PlannerDep, proposal_id: str, body: ProposalDecision) -> Decided:
    """W6: mark a proposal accepted or dismissed. Acting on it is a separate, validated change."""
    if not any(p.id == proposal_id for p in planning.proposals(c.session, c.user.department_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        p = planning.decide_proposal(c.session, proposal_id, body.accept, c.clock.now())
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    record(c, f"proposal.{p.status}", "proposal", p.id)
    return Decided(id=p.id, status=p.status)


# --- W7 Ausfälle live, W7b Eskalation ---------------------------------------------------------


class OfferStep(BaseModel):
    """One step of a cascade's timeline."""

    staff_name: str | None
    rank: int
    asked_at: datetime
    deadline_at: datetime | None
    responded_at: datetime | None
    response: str


class CascadeOut(BaseModel):
    """W7: a cover search as a timeline."""

    id: str
    date: date
    shift_type: str
    absent_staff: str | None
    opened_at: datetime
    status: str
    outcome: str | None
    covered_by: str | None
    escalation_reason: str | None
    remaining_candidates: int
    timeline: list[OfferStep]


def _cascade_out(c: Ctx, cas: operations.Cascade) -> CascadeOut:
    dep = department(c)
    a = planning.assignment(c.session, cas.assignment_id)
    assert a is not None
    absent = next(
        (
            x.staff_id
            for x in operations.absences(c.session, list(dep.staff), a.day, a.day)
            if x.id == cas.absence_id
        ),
        None,
    )
    return CascadeOut(
        id=cas.id,
        date=a.day,
        shift_type=a.shift_type,
        absent_staff=dep.name(absent),
        opened_at=cas.opened_at,
        status=cas.status,
        outcome=cas.outcome,
        covered_by=dep.name(cas.covered_by),
        escalation_reason=cas.escalation_reason,
        remaining_candidates=len(cas.queue),
        timeline=[
            OfferStep(
                staff_name=dep.name(o.staff_id),
                rank=o.rank,
                asked_at=o.asked_at,
                deadline_at=o.deadline_at,
                responded_at=o.responded_at,
                response=o.response,
            )
            for o in cas.offers
        ],
    )


@router.get("/planner/cascades")
def live_cascades(c: CtxDep, _: PlannerDep) -> list[CascadeOut]:
    """W7: open and escalated cover searches, and those closed in the last 7 days."""
    now = c.clock.now()
    settle_timers(c)
    active = operations.cascades(c.session, statuses=["open", "pending_approval"])
    recent = [
        x
        for x in operations.cascades(c.session, statuses=["closed"], since=now - timedelta(days=7))
        if x.closed_at and x.closed_at <= now
    ]
    dep = department(c)
    out = []
    for cas in active + recent:
        a = planning.assignment(c.session, cas.assignment_id)
        if a and a.staff_id in dep.staff:
            out.append(_cascade_out(c, cas))
    return out


class Option(BaseModel):
    """W7b: one way to close a gap, with its consequence."""

    kind: Literal["confirm_cover", "assign", "locum", "unfilled"]
    staff_id: str | None = None
    staff_name: str | None = None
    hours_after: float | None = None
    contract_hours: float | None = None
    overtime_after: float | None = None
    check: str = CHECK


class EscalationOut(BaseModel):
    """W7b: a cover search with ranked options."""

    cascade: CascadeOut
    options: list[Option]
    engine: EngineLabel


def _cascade_or_404(c: Ctx, cascade_id: str) -> operations.Cascade:
    cas = operations.cascade(c.session, cascade_id)
    dep = department(c)
    a = None if cas is None else planning.assignment(c.session, cas.assignment_id)
    if cas is None or a is None or a.staff_id not in dep.staff:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return cas


@router.get("/planner/cascades/{cascade_id}")
def escalation(c: CtxDep, _: PlannerDep, cascade_id: str) -> EscalationOut:
    """W7b: options to close the gap, ranked, with hours and overtime consequences."""
    settle_timers(c)
    cas = _cascade_or_404(c, cascade_id)
    dep = department(c)
    a = planning.assignment(c.session, cas.assignment_id)
    assert a is not None
    options: list[Option] = []
    if cas.status == "pending_approval" and cas.covered_by:
        options.append(
            Option(
                kind="confirm_cover", staff_id=cas.covered_by, staff_name=dep.name(cas.covered_by)
            )
        )
    if cas.status != "closed":
        m = month_start(a.day)
        shifts = effective(c.session, m, month_end(m))
        probe = Shift(a.id, a.day, a.shift_type, None, a.staff_id, "open")
        asked = {o.staff_id for o in cas.offers}
        people = [p for p in valid_takers(c, dep, probe, exclude={a.staff_id}) if p.id not in asked]
        rules = organization.rules_for(c.session, m).rules
        holidays = set(organization.holidays(c.session, m, month_end(m)))
        leave = approved_leave_days(c.session, [p.id for p in people], m, month_end(m))
        types = organization.shift_types(c.session)
        for cand in ranked(c, dep, people, a.day, a.shift_type)[:5]:
            h = hours_for(
                dep.staff[cand.staff_id],
                m,
                shifts,
                leave.get(cand.staff_id, set()),
                holidays,
                rules,
                types,
                c.clock.now(),
            )
            after = round(h.planned_hours + credit(a.shift_type, rules), 2)
            options.append(
                Option(
                    kind="assign",
                    staff_id=cand.staff_id,
                    staff_name=dep.name(cand.staff_id),
                    hours_after=after,
                    contract_hours=h.contract_hours,
                    overtime_after=round(max(0.0, after + h.leave_credit - h.contract_hours), 2),
                )
            )
        options += [Option(kind="locum"), Option(kind="unfilled")]
    return EscalationOut(
        cascade=_cascade_out(c, cas), options=options, engine=label(c.engines.cover_ranker.info)
    )


class CascadeDecision(BaseModel):
    """The Planner's choice for a gap."""

    option: Literal["confirm_cover", "assign", "locum", "unfilled"]
    staff_id: str | None = None


@router.post("/planner/cascades/{cascade_id}/decision")
def decide_cascade(c: CtxDep, _: PlannerDep, cascade_id: str, body: CascadeDecision) -> CascadeOut:
    """W7b: close a cover search the way the Planner chose."""
    cas = _cascade_or_404(c, cascade_id)
    dep = department(c)
    if body.option == "assign":
        if not body.staff_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a colleague")
        in_department(dep, body.staff_id)
    outcome = {
        "confirm_cover": "covered",
        "assign": "escalated_overtime",
        "locum": "locum",
        "unfilled": "unfilled",
    }
    if body.option == "confirm_cover" and not cas.covered_by:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nobody has accepted")
    taker = body.staff_id if body.option == "assign" else cas.covered_by
    if body.option in ("confirm_cover", "assign") and taker:
        a = planning.assignment(c.session, cas.assignment_id)
        assert a is not None
        introduced = change_violations(
            c,
            Inputs(c.session, dep, c.clock.now()),
            [],
            [Assignment(taker, a.day, a.shift_type)],
            {taker},
        )
        if introduced:
            raise _unprocessable(dep, "This cover breaks a rule", introduced)
    try:
        closed = operations.decide_cascade(
            c.session,
            cascade_id,
            outcome[body.option],
            body.staff_id if body.option == "assign" else None,
            c.clock.now(),
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    record(
        c,
        "cover.decided",
        "cover_cascade",
        cascade_id,
        closed.covered_by,
        {"outcome": closed.outcome},
    )
    return _cascade_out(c, closed)


# --- W8 Fairness und Compliance; W12 hours ----------------------------------------------------


class PersonBurden(BaseModel):
    """One physician's burden (Planner only)."""

    staff_id: str
    display_name: str
    nights: int
    weekends: int
    holidays: int


class DistributionOut(BaseModel):
    """Anonymous department statistics of one metric (nights, weekends, holidays)."""

    metric: str
    people: int
    mean: float
    median: float
    minimum: int
    maximum: int
    values: list[int]


class FairnessOut(BaseModel):
    """W8: burden distribution. Names only for the Planner; Oversight gets statistics only."""

    year: int
    as_of: date
    distributions: list[DistributionOut]
    people: list[PersonBurden] | None


@router.get("/fairness")
def fairness_report(c: CtxDep, user: OversightReaderDep, year: int | None = None) -> FairnessOut:
    """W8 (Planner) and W12 (Oversight, without names)."""
    y = year or c.clock.today().year
    counts, people, as_of = year_burden(c, y)
    dists = [
        DistributionOut(
            metric=d.category,
            people=d.people,
            mean=d.mean,
            median=d.median,
            minimum=d.minimum,
            maximum=d.maximum,
            values=list(d.values),
        )
        for d in (fairness.distribution(counts, people, cat) for cat in fairness.CATEGORIES)
    ]
    named = None
    if user.role == "planner":
        dep = department(c)
        named = [
            PersonBurden(
                staff_id=p,
                display_name=dep.name(p) or "",
                **counts.get(p, fairness.Burden()).__dict__,
            )
            for p in people
        ]
        named.sort(key=lambda x: x.display_name)
    return FairnessOut(year=y, as_of=as_of, distributions=dists, people=named)


class PersonHours(HoursOut):
    """A physician's hours in a month (Planner and Oversight: payroll, working-time records)."""

    staff_id: str
    display_name: str


class HoursReport(BaseModel):
    """W8/W12: hours, overtime and rest compliance per person for a month."""

    roster_month: date
    people: list[PersonHours]
    total_overtime_hours: float
    rest_violations_total: int = Field(description="Rest periods below the minimum (C2)")


@router.get("/compliance/hours")
def hours_report(c: CtxDep, _: OversightReaderDep, month: Month, rest: bool = True) -> HoursReport:
    """Per-person hours, overtime and rest compliance (C2) of a month (Planner and Oversight)."""
    m = parse_month(month)
    dep = department(c)
    banded = ("facharzt", "assistenzarzt", "oberarzt")
    people = sorted(
        (
            p
            for p in dep.staff.values()
            if p.role_on(month_end(m)) in banded or p.role_on(m) in banded
        ),
        key=lambda s: s.display_name,
    )
    table = hours_table(c, m, [p.id for p in people], rest=rest)
    out = [
        PersonHours(staff_id=p.id, display_name=p.display_name, **table[p.id].model_dump())
        for p in people
    ]
    return HoursReport(
        roster_month=m,
        people=out,
        total_overtime_hours=round(sum(p.overtime_hours for p in out), 2),
        rest_violations_total=sum(
            p.rest_compliance.violations for p in out if p.rest_compliance is not None
        ),
    )


class OvertimeMonth(BaseModel):
    """Department overtime in one month."""

    roster_month: date
    overtime_hours: float


@router.get("/compliance/overtime-trend")
def overtime_trend(
    c: CtxDep, _: OversightReaderDep, months: int = Query(12, ge=1, le=24)
) -> list[OvertimeMonth]:
    """W8: department overtime per month for the last published months."""
    published = [
        m for m in planning.published_months(c.session) if m <= month_start(c.clock.today())
    ][-months:]
    return [
        OvertimeMonth(
            roster_month=m,
            overtime_hours=hours_report(c, _, m.strftime("%Y-%m"), rest=False).total_overtime_hours,
        )
        for m in published
    ]
