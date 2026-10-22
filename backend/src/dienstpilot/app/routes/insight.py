"""Copilot (W9), audit (W10), master data (W11), oversight (W12), transparency (W13)."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from dienstpilot.app.common import EngineLabel, department, label, record, settle_timers
from dienstpilot.app.context import CtxDep
from dienstpilot.app.deps import AdminDep, MasterDataReaderDep, OversightReaderDep, PlannerDep
from dienstpilot.app.privacy import audit_payload_for
from dienstpilot.app.roster import approved_leave_days, effective, hours_for, month_end, month_start
from dienstpilot.app.routes.planner import (
    DistributionOut,
    HoursReport,
    fairness_report,
    hours_report,
)
from dienstpilot.audit import service as audit
from dienstpilot.organization import service as organization
from dienstpilot.planning import service as planning
from dienstpilot.shared.ports import CopilotFacts

router = APIRouter(tags=["insight"])
EVAL_RESULTS = Path(__file__).resolve().parents[5] / "eval" / "results"


# --- W9 Copilot -------------------------------------------------------------------------------


class AskIn(BaseModel):
    """A question for the copilot."""

    question: str = Field(max_length=500)
    language: Literal["de", "en"] = "de"


class AskOut(BaseModel):
    """The copilot's answer with figures and cited rules."""

    answer: str
    figures: dict[str, Any]
    citations: list[str]
    understood: bool
    engine: EngineLabel


@router.post("/copilot/ask")
def ask(c: CtxDep, _: OversightReaderDep, body: AskIn) -> AskOut:
    """W9: ask the copilot (stand-in). It reads; it cannot publish or approve anything."""
    dep = department(c)
    today = c.clock.today()
    months = planning.published_months(c.session)[-4:]  # the last four published months
    weekends: dict[tuple[str, date], int] = {}
    hours: dict[tuple[str, date], float] = {}
    types = organization.shift_types(c.session)
    for m in months:
        shifts = effective(c.session, m, month_end(m))
        rules = organization.rules_for(c.session, m).rules
        holidays = set(organization.holidays(c.session, m, month_end(m)))
        leave = approved_leave_days(c.session, list(dep.staff), m, month_end(m))
        for p in dep.staff.values():
            mine = [s for s in shifts if s.holder == p.id]
            weekends[(p.id, m)] = len(
                {s.day.toordinal() - s.day.weekday() for s in mine if s.day.weekday() >= 5}
            )
            if mine:
                hours[(p.id, m)] = hours_for(
                    p, m, shifts, leave.get(p.id, set()), holidays, rules, types, c.clock.now()
                ).planned_hours
    rs = organization.rules_for(c.session, today)
    facts = CopilotFacts(
        {p.id: p.display_name for p in dep.staff.values()},
        weekends,
        hours,
        months,
        rs.rules,
        rs.version,
        month_start(today),
    )
    a = c.engines.copilot.ask(body.question, body.language, facts)
    return AskOut(
        answer=a.answer,
        figures=a.figures,
        citations=a.citations,
        understood=a.understood,
        engine=label(c.engines.copilot.info),
    )


class ProposalIn(BaseModel):
    """W9 "Vorschlag erstellen": a proposal for the Planner's inbox."""

    title: str = Field(max_length=200)
    body: str = Field(max_length=4000)
    roster_month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")


class ProposalCreated(BaseModel):
    """The created proposal."""

    id: str
    status: str


@router.post("/copilot/proposals", status_code=status.HTTP_201_CREATED)
def create_proposal(c: CtxDep, _: PlannerDep, body: ProposalIn) -> ProposalCreated:
    """W9: create a proposal. It changes nothing until the Planner acts on it."""
    m = None
    if body.roster_month:
        y, mm = body.roster_month.split("-")
        m = date(int(y), int(mm), 1)
    p = planning.create_proposal(
        c.session,
        department_id=c.user.department_id,
        roster_month=m,
        created_by=c.user.id,
        source="copilot",
        title=body.title,
        body=body.body,
        now=c.clock.now(),
    )
    record(c, "proposal.created", "proposal", p.id, payload={"title": p.title})
    return ProposalCreated(id=p.id, status=p.status)


# --- W10 Protokoll ----------------------------------------------------------------------------


class AuditEventOut(BaseModel):
    """An audit event as the viewer may see it."""

    id: str
    occurred_at: datetime
    actor: str
    action: str
    subject_type: str
    subject_id: str | None
    staff_name: str | None
    payload: dict[str, Any]
    seq: int
    hash: str


class ChainOut(BaseModel):
    """What the log may claim about itself: the result of the last real verification."""

    state: Literal["verified", "stale", "failed", "never_checked"]
    checked_at: datetime | None = None
    trigger: Literal["nightly", "on_demand", "seed"] | None = None
    rows: int = 0
    newer_events: int = Field(0, description="Entries appended since the check; each links up")
    head_hash: str | None = None
    first_bad_seq: int | None = None
    reason: str | None = None


class AuditPage(BaseModel):
    """W10: a page of the audit trail."""

    total: int
    events: list[AuditEventOut]
    chain: ChainOut


@router.get("/audit/events")
def audit_events(
    c: CtxDep,
    _: OversightReaderDep,
    action: str | None = None,
    staff_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    """W10: the audit trail, filterable.

    Same privacy rules as everywhere: no absence category for anyone but the Planner.
    """
    settle_timers(c)
    dep = department(c)
    total, events = audit.list_events(
        c.session,
        c.user.department_id,
        action_prefix=action,
        staff_id=staff_id,
        since=since,
        until=until or c.clock.now(),
        limit=limit,
        offset=offset,
    )
    return AuditPage(
        total=total,
        events=[
            AuditEventOut(
                id=e.id,
                occurred_at=e.occurred_at,
                actor=e.actor_label,
                action=e.action,
                subject_type=e.subject_type,
                subject_id=e.subject_id,
                staff_name=dep.name(e.staff_id),
                payload=audit_payload_for(c.user, e.action, e.payload),
                seq=e.seq,
                hash=e.hash,
            )
            for e in events
        ],
        chain=_chain_out(audit.chain_status(c.session, c.user.department_id, c.clock.now())),
    )


def _chain_out(st: audit.ChainStatus) -> ChainOut:
    return ChainOut(
        state=st.state,
        checked_at=st.checked_at,
        trigger=st.trigger,
        rows=st.rows,
        newer_events=st.newer_events,
        head_hash=st.head_hash,
        first_bad_seq=st.first_bad_seq,
        reason=st.reason,
    )


@router.post("/audit/verify")
def audit_verify(c: CtxDep, _: OversightReaderDep) -> ChainOut:
    """W10: verify the whole hash chain now (Planner or Oversight) and return the result."""
    settle_timers(c)
    audit.run_check(c.session, c.user.department_id, c.clock.now(), "on_demand")
    return _chain_out(audit.chain_status(c.session, c.user.department_id, c.clock.now()))


# --- W11 Regeln und Stammdaten ----------------------------------------------------------------


class RuleSetOut(BaseModel):
    """A rule-set version."""

    version: str
    effective_from: date
    rules: dict[str, Any]
    change_note_de: str
    change_note_en: str


class ShiftTypeOut(BaseModel):
    """A shift type."""

    code: str
    letter_de: str
    letter_en: str
    name_de: str
    name_en: str
    start_time: str | None
    end_time: str | None
    ends_next_day: bool
    net_hours: float
    kind: str
    burden_weight: float


class ContractOut(BaseModel):
    """A physician's current contract."""

    staff_id: str
    display_name: str
    role: str
    title_de: str
    title_en: str
    weekly_hours: float
    qualifications: list[str]


class DemandOut(BaseModel):
    """The demand rows of one example day."""

    date: date
    rows: list[tuple[str, str, int]]


class MasterData(BaseModel):
    """W11: shift types, qualifications, contracts, demand templates, rule versions."""

    shift_types: list[ShiftTypeOut]
    qualifications: list[tuple[str, str, str]]
    contracts: list[ContractOut]
    demand_examples: list[DemandOut]
    rule_sets: list[RuleSetOut]


@router.get("/master-data")
def master_data(c: CtxDep, _: MasterDataReaderDep) -> MasterData:
    """W11: master data and versioned rules (Administrator and Planner)."""
    today = c.clock.today()
    dep = department(c)
    contracts = []
    for p in sorted(dep.rostered(today), key=lambda s: s.display_name):
        k = p.contract_on(today)
        assert k is not None
        quals = sorted(
            q for q, a, b in p.qualifications if a <= today and (b is None or today <= b)
        )
        contracts.append(
            ContractOut(
                staff_id=p.id,
                display_name=p.display_name,
                role=k.role,
                title_de=k.title_de,
                title_en=k.title_en,
                weekly_hours=k.weekly_hours,
                qualifications=quals,
            )
        )
    demand = organization.demand(c.session, today, today + timedelta(days=6))
    return MasterData(
        shift_types=[
            ShiftTypeOut(
                code=s.code,
                letter_de=s.letter_de,
                letter_en=s.letter_en,
                name_de=s.name_de,
                name_en=s.name_en,
                start_time=None if s.start_time is None else s.start_time.isoformat("minutes"),
                end_time=None if s.end_time is None else s.end_time.isoformat("minutes"),
                ends_next_day=s.ends_next_day,
                net_hours=s.net_hours,
                kind=s.kind,
                burden_weight=s.burden_weight,
            )
            for s in organization.shift_types(c.session).values()
        ],
        qualifications=organization.qualifications(c.session),
        contracts=contracts,
        demand_examples=[DemandOut(date=d, rows=rows) for d, rows in sorted(demand.items())],
        rule_sets=[
            RuleSetOut(
                version=r.version,
                effective_from=r.effective_from,
                rules=r.rules,
                change_note_de=r.change_note_de,
                change_note_en=r.change_note_en,
            )
            for r in organization.rule_sets(c.session)
        ],
    )


class RuleSetIn(BaseModel):
    """A new rule version: the full set of rules, effective from a future date."""

    version: str = Field(pattern=r"^\d{4}-\d+$")
    effective_from: date
    rules: dict[str, Any]
    change_note_de: str = Field(max_length=300)
    change_note_en: str = Field(max_length=300)


@router.post("/admin/rule-sets", status_code=status.HTTP_201_CREATED)
def add_rule_set(c: CtxDep, _: AdminDep, body: RuleSetIn) -> RuleSetOut:
    """W11: add a rule version ("Neue Regelversion ab 01.01.2027"). Old rosters keep theirs."""
    existing = organization.rule_sets(c.session)
    if body.effective_from <= c.clock.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "A new version must start in the future"
        )
    if any(r.version == body.version for r in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "Version exists")
    missing = set(existing[-1].rules) - set(body.rules)
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Rules missing: {sorted(missing)}"
        )
    r = organization.add_rule_set(
        c.session,
        body.version,
        body.effective_from,
        body.rules,
        body.change_note_de,
        body.change_note_en,
    )
    record(
        c,
        "rule_set.added",
        "rule_set",
        r.id,
        payload={"version": r.version, "effective_from": r.effective_from.isoformat()},
    )
    return RuleSetOut(
        version=r.version,
        effective_from=r.effective_from,
        rules=r.rules,
        change_note_de=r.change_note_de,
        change_note_en=r.change_note_en,
    )


# --- W12 Aufsicht -----------------------------------------------------------------------------


class OversightSummary(BaseModel):
    """W12: read-only view for Klinikleitung, HR and works council."""

    read_only: bool = True
    roster_month: date
    hours: HoursReport
    fairness: list[DistributionOut]
    cost: None = Field(None, description="Cost is not modelled in the synthetic data")
    audit_export: str = "/audit/export"


@router.get("/oversight/summary")
def oversight_summary(
    c: CtxDep,
    user: OversightReaderDep,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> OversightSummary:
    """W12: hours and overtime per person, fairness as anonymous statistics, audit export."""
    m = month or month_start(c.clock.today()).strftime("%Y-%m")
    hours = hours_report(c, user, m)
    fair = fairness_report(c, user)
    y, mm = m.split("-")
    return OversightSummary(
        roster_month=date(int(y), int(mm), 1), hours=hours, fairness=fair.distributions
    )


@router.get("/audit/export")
def audit_export(
    c: CtxDep,
    user: OversightReaderDep,
    since: datetime | None = None,
    until: datetime | None = None,
) -> AuditPage:
    """W12: export of the audit trail (same privacy rules), up to 5 000 events."""
    pages: list[AuditEventOut] = []
    last: AuditPage | None = None
    for offset in range(0, 5000, 500):
        last = audit_events(c, user, since=since, until=until, limit=500, offset=offset)
        pages += last.events
        if len(last.events) < 500:
            break
    assert last is not None
    return AuditPage(total=last.total, events=pages, chain=last.chain)


# --- W13 KI-Transparenz -----------------------------------------------------------------------


class ComponentOut(BaseModel):
    """W13: one component card."""

    component: str
    kind: str
    implementation: str
    version: str
    note: str
    planned_phase: int | None
    can_change_roster: bool = False
    eval_metric: dict[str, Any] | None = Field(
        None,
        description="Written by an eval/ script (eval/results/c1.json …); None until then",
    )


KINDS = {
    "C1": "optimization",
    "C2": "deterministic",
    "C3": "ml",
    "C4": "ml",
    "C5": "ml",
    "C6": "ml",
    "C7": "llm",
    "C8": "llm",
}


@router.get("/transparency/components")
def components(c: CtxDep) -> list[ComponentOut]:
    """W13: what each component is, how far it is built, and that none can change the roster."""
    out = []
    for info in c.engines.infos():
        metric = None
        result = EVAL_RESULTS / f"{info.component.lower()}.json"
        if result.exists():
            metric = json.loads(result.read_text(encoding="utf-8"))
        out.append(
            ComponentOut(
                component=info.component,
                kind=KINDS[info.component],
                implementation=info.implementation,
                version=info.version,
                note=info.note,
                planned_phase=info.planned_phase,
                eval_metric=metric,
            )
        )
    return out
