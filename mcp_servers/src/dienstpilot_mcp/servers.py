"""The five servers and their tools. Each tool is a typed wrapper over one REST endpoint.

Which role sees which tool is decided here (the list a client gets is already role-scoped) and,
independently, by the API (a call the role may not make is answered 403). The roles of the demo:
``planner`` (everything below) and ``oversight`` (read-only tools). Staff roles get no MCP access.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from dienstpilot_mcp import models as m
from dienstpilot_mcp.backend_client import Backend

PLANNER = frozenset({"planner"})
READERS = frozenset({"planner", "oversight"})
FORBIDDEN_NAMES = re.compile(
    r"publish|approve|send|decide|decision|apply|accept|close|delete|release"
)
MONTH = r"^\d{4}-\d{2}$"


class AddShift(BaseModel):
    """A shift to add."""

    date: date
    shift_type: str
    staff_id: str


class Change(BaseModel):
    """One change to a published roster: reassign or remove a shift, or add one."""

    assignment_id: str | None = Field(None, description="The shift to reassign or remove")
    new_staff_id: str | None = Field(None, description="The new holder; null removes the shift")
    add: AddShift | None = Field(None, description="A shift to add (instead of assignment_id)")


@dataclass(frozen=True)
class ToolSpec:
    """One tool: its callable, who may list it, and what it does to the system."""

    name: str
    fn: Callable[..., Awaitable[Any]]
    description: str
    roles: frozenset[str]
    read_only: bool

    @property
    def annotations(self) -> ToolAnnotations:
        """The MCP annotations: reads are read-only; the only write creates a proposal."""
        return ToolAnnotations(
            title=self.name,
            readOnlyHint=self.read_only,
            destructiveHint=False,
            idempotentHint=self.read_only,
            openWorldHint=False,
        )


def _violations(raw: list[dict[str, Any]]) -> list[m.Violation]:
    return [
        m.Violation(rule=v["rule"], staff_id=v.get("staff_id"), date=v["date"], params=v["params"])
        for v in raw
    ]


def _days(row: dict[str, Any]) -> list[m.ShiftDay]:
    return [
        m.ShiftDay(
            date=d,
            shifts=c["shifts"],
            assignment_ids=c["assignment_ids"],
            absent=c.get("absence") is not None,  # the category never leaves the API's reader
            on_leave=c["on_leave"],
        )
        for d, c in sorted(row["cells"].items())
        if c["shifts"] or c.get("absence") or c["on_leave"]
    ]


def _row(x: dict[str, Any]) -> m.RosterRow:
    days = _days(x)
    return m.RosterRow(staff_id=x["staff_id"], totals=m.totals_of(days), days=days)


def build(b: Backend) -> dict[str, list[ToolSpec]]:
    """Return the tools of every server, bound to a backend."""

    async def get_roster(month: str = Field(pattern=MONTH)) -> m.Roster:
        """Return the department's month: shifts per physician and coverage (staff ids only)."""
        r = await b.get("/roster", month=month)
        return m.Roster(
            roster_month=r["roster_month"],
            status=r["status"],
            rule_set_version=r["rule_set_version"],
            rows=[_row(x) for x in r["rows"]],
            coverage=[m.CoverageRow(**c) for c in r["coverage"]],
        )

    async def get_assignments_for(
        staff_id: str, month: str = Field(pattern=MONTH)
    ) -> m.Assignments:
        """Return one physician's shifts in a month."""
        r = await b.get("/roster", month=month)
        row = next((x for x in r["rows"] if x["staff_id"] == staff_id), None)
        days = [] if row is None else _days(row)
        return m.Assignments(
            staff_id=staff_id,
            roster_month=r["roster_month"],
            totals=m.totals_of(days),
            days=days,
        )

    async def get_burden_ledger(year: int | None = None) -> m.BurdenLedger:
        """Return nights, weekends and holidays so far this year (per person: Planner only)."""
        r = await b.get("/fairness", year=year)
        people = r.get("people")
        return m.BurdenLedger(
            year=r["year"],
            as_of=r["as_of"],
            distributions=[
                m.Distribution(
                    metric=d["metric"],
                    people=d["people"],
                    mean=d["mean"],
                    median=d["median"],
                    minimum=d["minimum"],
                    maximum=d["maximum"],
                )
                for d in r["distributions"]
            ],
            people=None
            if people is None
            else [
                m.PersonBurden(
                    staff_id=p["staff_id"],
                    nights=p["nights"],
                    weekends=p["weekends"],
                    holidays=p["holidays"],
                )
                for p in people
            ],
        )

    async def get_coverage(month: str = Field(pattern=MONTH)) -> m.Coverage:
        """Return demand against assigned physicians per day, shift and qualification."""
        r = await b.get("/roster", month=month)
        rows = [m.CoverageRow(**c) for c in r["coverage"]]
        return m.Coverage(
            roster_month=r["roster_month"],
            rows=rows,
            short=[x for x in rows if x.assigned < x.required],
        )

    async def run_what_if(changes: list[Change]) -> m.WhatIf:
        """Check changes to published rosters with C2. Nothing is written."""
        r = await b.post(
            "/planner/what-if",
            {"changes": [c.model_dump(mode="json", exclude_none=True) for c in changes]},
        )
        return m.WhatIf(
            valid=r["valid"],
            introduced=_violations(r["introduced"]),
            hours_delta={p["staff_id"]: p["hours_delta"] for p in r["people"]},
            uncovered=[
                {"date": g["date"], "shift_type": g["shift_type"]}
                for g in r["removed_without_replacement"]
            ],
            validator_version=r["validator"]["version"],
        )

    async def validate(
        roster_month: str = Field(pattern=MONTH), variant_id: str | None = None
    ) -> m.Validation:
        """Return every rule violation C2 finds in a month's roster or a draft variant."""
        r = await b.post(
            "/planner/validate", {"roster_month": roster_month, "variant_id": variant_id}
        )
        return m.Validation(
            roster_month=r["roster_month"],
            valid=r["valid"],
            violations=_violations(r["violations"]),
        )

    async def get_variants(month: str = Field(pattern=MONTH)) -> m.Variants:
        """Return C1's newest run for a month with each variant's metrics (the numbers to quote)."""
        r = await b.get("/planner/runs", month=month)
        runs = [x for x in r["runs"] if x["variants"]] or r["runs"]
        run = runs[0] if runs else None
        return m.Variants(
            roster_month=r["roster_month"],
            run_id=None if run is None else run["run_id"],
            status=None if run is None else run["status"],
            variants=[]
            if run is None
            else [
                m.VariantSummary(
                    variant_id=v["variant_id"],
                    label=v["label"],
                    status=v["status"],
                    profile=v["profile"],
                    recommended=v["recommended"],
                    metrics=v["metrics"],
                )
                for v in run["variants"]
            ],
            solver_version=None if run is None else run["solver_version"],
            validator_version=None if run is None else run["validator_version"],
        )

    async def get_history(month: str = Field(pattern=MONTH)) -> m.History:
        """Return why a month looks as it does: changes, leave decisions, proposals (free text)."""
        r = await b.get("/planner/history", month=month)
        return m.History(
            roster_month=r["roster_month"][:7],
            changes=[
                m.HistoryChange(
                    change_id=x["change_id"],
                    date=x["date"],
                    shift_type=x["shift_type"],
                    kind=x["kind"],
                    staff_before=x["staff_before"],
                    staff_after=x["staff_after"],
                    reason=x["reason"],
                )
                for x in r["changes"]
            ],
            decisions=[
                m.HistoryDecision(
                    staff_id=x["staff_id"],
                    start_date=x["start_date"],
                    end_date=x["end_date"],
                    status=x["status"],
                    reason=x["reason"],
                )
                for x in r["decisions"]
            ],
            proposals=[
                m.HistoryProposal(
                    proposal_id=x["id"],
                    source=x["source"],
                    kind=x["kind"],
                    status=x["status"],
                    title=x["title"],
                    body=x["body"],
                )
                for x in r["proposals"]
            ],
        )

    async def create_proposal(
        title: str = Field(max_length=200),
        body: str = Field(max_length=4000),
        roster_month: str | None = Field(None, pattern=MONTH),
        changes: list[Change] | None = None,
    ) -> m.ProposalCreated:
        """Put a suggestion into the Planner's inbox. It changes nothing until the Planner acts."""
        r = await b.post(
            "/copilot/proposals",
            {
                "title": title,
                "body": body,
                "roster_month": roster_month,
                "kind": "change",
                "changes": None
                if changes is None
                else [c.model_dump(mode="json", exclude_none=True) for c in changes],
            },
        )
        return m.ProposalCreated(proposal_id=r["id"], status=r["status"], kind="change")

    async def search_rules(
        query: str = Field(min_length=3, max_length=400), k: int = 5
    ) -> m.RuleSearch:
        """Search the rulebook (ArbZG and the department's documents); results carry citations."""
        r = await b.get("/rules/search", q=query, k=k)
        return m.RuleSearch(
            query=query,
            found=r["found"],
            passages=[
                m.RulePassage(
                    id=p["id"],
                    citation=p["citation"],
                    text=p["text"],
                    synthetic=p["synthetic"],
                    language=p["language"],
                    cosine=p["cosine"],
                )
                for p in r["passages"]
            ],
            mode=r["mode"],
            configured=r["configured"],
            fallback=r["fallback"],
        )

    async def get_rule(rule_id: str) -> m.RulePassage:
        """Return one passage of the rulebook by id, for example ``arbzg:§5:1``."""
        p = await b.get(f"/rules/{rule_id}")
        return m.RulePassage(
            id=p["id"],
            citation=p["citation"],
            text=p["text"],
            synthetic=p["synthetic"],
            language=p["language"],
            cosine=None,
        )

    async def get_absence_forecast(days: int = Field(14, ge=1, le=14)) -> m.AbsenceForecast:
        """Return C3's expected absences per day for the department (never for one person)."""
        r = await b.get("/planner/overview")
        return m.AbsenceForecast(
            days=[
                m.DayForecast(
                    date=d["date"],
                    expected_absences=d["expected_absences"],
                    expected_low=d["expected_low"],
                    expected_high=d["expected_high"],
                    short=d["short"],
                )
                for d in r["coverage"][:days]
            ],
            forecaster=r["forecast_engine"]["implementation"]
            + " "
            + r["forecast_engine"]["version"],
        )

    async def get_cover_candidates(assignment_id: str) -> m.CoverCandidates:
        """Return colleagues who could take a shift: C2-validated, in C5's order (ids only)."""
        r = await b.get("/planner/cover-candidates", assignment_id=assignment_id)
        return m.CoverCandidates(
            assignment_id=r["assignment_id"],
            date=r["date"],
            shift_type=r["shift_type"],
            candidates=r["candidates"],
        )

    async def draft_announcement(
        audience: str = Field(max_length=80),
        title: str = Field(max_length=160),
        text: str = Field(max_length=3000),
    ) -> m.ProposalCreated:
        """Save a draft announcement in the Planner's inbox. Nothing is sent; a person must."""
        r = await b.post(
            "/copilot/proposals",
            {
                "title": f"Ankündigung: {title}",
                "body": f"Adressaten: {audience}\n\n{text}",
                "kind": "announcement",
            },
        )
        return m.ProposalCreated(proposal_id=r["id"], status=r["status"], kind="announcement")

    def t(
        name: str, fn: Callable[..., Awaitable[Any]], roles: frozenset[str], *, write: bool = False
    ) -> ToolSpec:
        return ToolSpec(name, fn, (fn.__doc__ or "").strip(), roles, not write)

    return {
        "roster": [
            t("get_roster", get_roster, READERS),
            t("get_assignments_for", get_assignments_for, READERS),
            t("get_burden_ledger", get_burden_ledger, READERS),
            t("get_coverage", get_coverage, READERS),
        ],
        "planning": [
            t("run_what_if", run_what_if, READERS),
            t("validate", validate, PLANNER),
            t("get_variants", get_variants, PLANNER),
            t("get_history", get_history, PLANNER),
            t("create_proposal", create_proposal, PLANNER, write=True),
        ],
        "rules": [t("search_rules", search_rules, READERS), t("get_rule", get_rule, READERS)],
        "forecast": [
            t("get_absence_forecast", get_absence_forecast, PLANNER),
            t("get_cover_candidates", get_cover_candidates, PLANNER),
        ],
        "notify": [t("draft_announcement", draft_announcement, PLANNER, write=True)],
    }


def make_server(name: str, role: str, specs: list[ToolSpec]) -> MCPServer:
    """Build one server as one role sees it (only the tools that role may list)."""
    server = MCPServer(
        name=f"dienstpilot-{name}", instructions=f"DienstPilot {name} tools ({role})."
    )
    for s in specs:
        if role in s.roles:
            if FORBIDDEN_NAMES.search(s.name):
                raise ValueError(f"tool name {s.name} suggests a power no tool may have")
            server.add_tool(s.fn, name=s.name, description=s.description, annotations=s.annotations)
    return server
