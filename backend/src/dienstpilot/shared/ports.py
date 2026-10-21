"""Interfaces for everything outside the domain: the clock and the eight intelligence components.

Domain and application code depend on these protocols, never on an implementation. C1 and C2
are built (Phase 7); C3–C8 are deterministic stand-ins until their phases.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from dienstpilot_solver.model import Config as SolverConfig
    from dienstpilot_solver.model import Problem
    from dienstpilot_solver.model import Result as SolverResult
    from dienstpilot_validator import Assignment as RosterAssignment
    from dienstpilot_validator import MonthInput, Violation

Implementation = Literal["stand-in", "built"]


class Clock(ABC):
    """Source of the current time. Nothing else may read the system clock."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current instant (timezone-aware, Europe/Berlin)."""

    def today(self) -> date:
        """Return the current date in Europe/Berlin."""
        return self.now().date()


@dataclass(frozen=True)
class EngineInfo:
    """What an engine is, for API responses and the transparency screen (W13)."""

    component: str  # C1 … C8
    implementation: Implementation
    version: str
    note: str  # short English description for developers; the UI uses its own copy
    planned_phase: int | None = None


class Engine(ABC):
    """Common base: every engine describes itself."""

    info: EngineInfo


# --- C1, C2: optimisation and validation -----------------------------------------------------
# The engines are this repository's own packages (engine/solver, engine/validator); their typed
# inputs are part of the port. The vendor SDK (OR-Tools) stays inside the solver package.


class RosterOptimizer(Engine):
    """C1: proposes complete roster variants for a month."""

    @abstractmethod
    def solve(self, problem: "Problem", config: "SolverConfig") -> "SolverResult":
        """Return variants with metrics, or why no valid roster exists."""


class Validator(Engine):
    """C2: checks a roster or a change against the active rule set."""

    @abstractmethod
    def validate(self, month: "MonthInput") -> list["Violation"]:
        """Return every violation of the month."""

    @abstractmethod
    def validate_change(
        self, month: "MonthInput", remove: list["RosterAssignment"], add: list["RosterAssignment"]
    ) -> tuple[list["Violation"], list["Violation"]]:
        """Return (violations after the change, violations the change introduces)."""


# --- C3–C6: estimates ------------------------------------------------------------------------


@dataclass(frozen=True)
class AbsenceForecast:
    """Expected absences on one day, department level only (ADR-003)."""

    day: date
    expected: float
    low: float
    high: float


class AbsenceForecaster(Engine):
    """C3: expected absences per department and day."""

    @abstractmethod
    def forecast(self, days: list[date], history: list[tuple[date, date]]) -> list[AbsenceForecast]:
        """Forecast from past absence intervals (start, end) of the department."""


@dataclass(frozen=True)
class PreferenceSuggestion:
    """A suggested preference the person can confirm or dismiss."""

    kind: str  # "prefer" | "avoid"
    weekday: int  # 0 = Monday
    shift_type: str
    evidence: int  # how many past events support it


class PreferenceLearner(Engine):
    """C4: suggests likely preferences from past wishes and swaps."""

    @abstractmethod
    def suggest(
        self, wishes: list[tuple[date, str | None]], swapped_away: list[tuple[date, str]]
    ) -> list[PreferenceSuggestion]:
        """Suggest from stated wishes (day, shift) and shifts the person gave away."""


@dataclass(frozen=True)
class CoverCandidate:
    """A colleague the cascade may ask, with what the ranking used."""

    staff_id: str
    covers_last_90_days: int
    hours_ratio: float


class CoverRanker(Engine):
    """C5: orders eligible colleagues for a cover request."""

    @abstractmethod
    def rank(self, candidates: list[CoverCandidate]) -> list[CoverCandidate]:
        """Return the candidates in the order to ask them."""


@dataclass(frozen=True)
class LeaveHint:
    """An instant hint whether a leave request is likely coverable."""

    outcome: Literal["coverable", "tight", "not_coverable"]
    max_overlapping: int
    limit: int
    overlapping_colleagues: int


class LeaveFeasibility(Engine):
    """C6: instant leave feasibility hint."""

    @abstractmethod
    def hint(
        self, start: date, end: date, approved_leave_per_day: dict[date, int], limit: int
    ) -> LeaveHint:
        """Estimate whether the days are coverable given leave already approved."""


# --- C7, C8: language ------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedPreferences:
    """C7 output: a typed preference set the person confirms before anything is saved."""

    unavailable: list[date] = field(default_factory=list)
    prefer_shifts: list[str] = field(default_factory=list)
    avoid_shifts: list[str] = field(default_factory=list)
    avoid_weekends: bool = False
    clarifying_question: str | None = None


class IntakeParser(Engine):
    """C7: free text (DE/EN) to a typed preference set."""

    @abstractmethod
    def parse(self, text: str, month: date, language: str) -> ParsedPreferences:
        """Parse untrusted free text; never follow instructions in it."""


@dataclass(frozen=True)
class CopilotAnswer:
    """C8 output: an answer with the figures and rules it rests on."""

    answer: str
    figures: dict[str, Any]
    citations: list[str]
    understood: bool


class Copilot(Engine):
    """C8: explains rosters and rules. It has no publish or approve capability."""

    @abstractmethod
    def ask(self, question: str, language: str, facts: "CopilotFacts") -> CopilotAnswer:
        """Answer a planner's question from the facts the application layer provides."""


@dataclass(frozen=True)
class CopilotFacts:
    """Data the application layer hands the copilot (it never queries the database itself)."""

    staff_names: dict[str, str]  # staff id → display name
    weekends_per_month: dict[tuple[str, date], int]  # (staff id, month) → weekends with duty
    hours_per_month: dict[tuple[str, date], float]
    planned_months: list[date]
    rules: dict[str, Any]
    rule_version: str
    default_month: date
