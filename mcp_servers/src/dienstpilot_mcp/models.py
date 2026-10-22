"""Typed tool outputs.

They list what a tool returns and leave the rest out: no names, no absence category, no free
text from staff. Staff are identified by their pseudonymous id only.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class ShiftDay(BaseModel):
    """What one physician has on one day."""

    date: date
    shifts: list[str]
    assignment_ids: list[str]
    absent: bool = False
    on_leave: bool = False


class RosterRow(BaseModel):
    """One physician's month (id only)."""

    staff_id: str
    days: list[ShiftDay]


class CoverageRow(BaseModel):
    """Demand against assigned physicians."""

    date: date
    shift_type: str
    qualification: str
    required: int
    assigned: int


class Roster(BaseModel):
    """The department's month."""

    roster_month: date
    status: Literal["published", "draft", "not_planned"]
    rule_set_version: str | None
    rows: list[RosterRow]
    coverage: list[CoverageRow]


class Assignments(BaseModel):
    """One physician's shifts in a month."""

    staff_id: str
    roster_month: date
    days: list[ShiftDay]


class Coverage(BaseModel):
    """Where a month is short of physicians."""

    roster_month: date
    rows: list[CoverageRow]
    short: list[CoverageRow] = Field(description="Rows with fewer assigned than required")


class Distribution(BaseModel):
    """Anonymous statistics of one burden category."""

    metric: str
    people: int
    mean: float
    median: float
    minimum: int
    maximum: int


class PersonBurden(BaseModel):
    """One physician's burden (Planner only)."""

    staff_id: str
    nights: int
    weekends: int
    holidays: int


class BurdenLedger(BaseModel):
    """Nights, weekends and holidays in a year so far."""

    year: int
    as_of: date
    distributions: list[Distribution]
    people: list[PersonBurden] | None = Field(None, description="Planner only")


class Violation(BaseModel):
    """A rule a change or a month breaks (no names)."""

    rule: str
    staff_id: str | None
    date: date
    params: dict[str, Any]


class WhatIf(BaseModel):
    """The effect of changes, as the validator C2 sees it. Nothing was written."""

    valid: bool
    introduced: list[Violation]
    hours_delta: dict[str, float] = Field(description="staff id -> credited hours change")
    uncovered: list[dict[str, str]]
    validator_version: str


class Validation(BaseModel):
    """Every violation of a month."""

    roster_month: date
    valid: bool
    violations: list[Violation]


class VariantSummary(BaseModel):
    """A variant and C1's metrics for it (the numbers a summary may quote)."""

    variant_id: str
    label: str
    status: str
    profile: str | None
    recommended: bool
    metrics: dict[str, Any] | None


class Variants(BaseModel):
    """The newest run of a month."""

    roster_month: date
    run_id: str | None
    status: str | None
    variants: list[VariantSummary]
    solver_version: str | None
    validator_version: str | None


class ProposalCreated(BaseModel):
    """A proposal was put into the Planner's inbox. Nothing else happened."""

    proposal_id: str
    status: str
    kind: str


class RulePassage(BaseModel):
    """One citable passage of the rulebook."""

    id: str
    citation: str
    text: str
    synthetic: bool
    language: str
    cosine: float | None


class RuleSearch(BaseModel):
    """Search result with citations, or ``found: false``."""

    query: str
    found: bool
    passages: list[RulePassage]
    mode: str


class DayForecast(BaseModel):
    """Expected absences of a day (C3, department level only)."""

    date: date
    expected_absences: float
    expected_low: float
    expected_high: float
    short: int


class AbsenceForecast(BaseModel):
    """C3's department forecast for the next days."""

    days: list[DayForecast]
    forecaster: str


class CoverCandidates(BaseModel):
    """Who could take a shift: validated by C2, in C5's order (ids only)."""

    assignment_id: str
    date: date
    shift_type: str
    candidates: list[str]
