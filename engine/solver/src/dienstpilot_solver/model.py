"""Inputs, configuration and results of the optimizer. Independent of the validator's types."""

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any


@dataclass(frozen=True)
class Shift:
    """A shift type with clock times and net hours."""

    code: str
    start: time
    end: time
    ends_next_day: bool
    net_hours: float


@dataclass(frozen=True)
class Doctor:
    """A physician: contract periods (role, weekly hours), qualifications, rotations."""

    id: str
    contracts: tuple[tuple[str, float, date, date | None], ...]
    qualifications: tuple[tuple[str, date, date | None], ...] = ()
    rotations: tuple[tuple[date, date], ...] = ()

    def contract(self, d: date) -> tuple[str, float] | None:
        """Return (role, weekly hours) on d."""
        for role, hours, a, b in self.contracts:
            if a <= d and (b is None or d <= b):
                return role, hours
        return None

    def available(self, d: date) -> bool:
        """Return whether the physician is on the department's roster on d."""
        return self.contract(d) is not None and not any(a <= d <= b for a, b in self.rotations)

    def holds(self, q: str, d: date) -> bool:
        """Return whether the physician holds qualification q on d."""
        return any(x == q and a <= d and (b is None or d <= b) for x, a, b in self.qualifications)


@dataclass(frozen=True)
class WishIn:
    """A "möchte arbeiten" entry (shift None: any shift that day)."""

    staff_id: str
    day: date
    shift: str | None
    important: bool


@dataclass(frozen=True)
class Commitment:
    """A binding promise, e.g. a leave trade-off: at least ``weekends`` weekends with duty."""

    staff_id: str
    weekends: int


@dataclass(frozen=True)
class Problem:
    """Everything the optimizer needs for one month."""

    month: date
    rules: dict[str, Any]
    shifts: dict[str, Shift]
    doctors: dict[str, Doctor]
    demand: dict[date, list[tuple[str, str, int]]]
    holidays: frozenset[date]
    leave: dict[str, frozenset[date]]
    blocked: dict[str, frozenset[date]]
    history: tuple[tuple[str, date, str], ...]  # the seven days before the month, as worked
    wishes: tuple[WishIn, ...] = ()
    ytd: dict[str, tuple[int, int, int]] = field(default_factory=dict)  # nights, weekends, holidays
    prior: tuple[tuple[str, date, str], ...] = ()  # a previous plan to stay close to (stability)
    commitments: tuple[Commitment, ...] = ()


@dataclass(frozen=True)
class Profile:
    """Weights of the soft objectives (per unit: wish, burden point, overtime hour, night, change)."""

    name: str
    wishes: int
    spread: int
    overtime: int
    isolated_nights: int
    stability: int


PROFILES: tuple[Profile, ...] = (
    Profile("wishes_first", wishes=12, spread=3, overtime=1, isolated_nights=2, stability=1),
    Profile("zero_overtime", wishes=4, spread=3, overtime=12, isolated_nights=2, stability=1),
    # Tuned on July–December 2024 (eval/tune_profiles.py, eval/results/tuning.json).
    Profile("balanced", wishes=8, spread=5, overtime=3, isolated_nights=2, stability=1),
)


@dataclass(frozen=True)
class Config:
    """Solver settings. Deterministic time makes runs reproducible; wall time is only a guard."""

    deterministic_time: float = 20.0  # CP-SAT deterministic seconds per variant
    max_wall_seconds: float = 120.0
    workers: int = 8
    seed: int = 20261020
    variants: int = 3
    min_difference: float = 0.05  # share of assignments each later variant must change
    important_wish_weight: int = 3
    extra_day_shifts: int = 3  # Früh/Spät beyond the minimum demand (to reach the hours floor)
    burden_weights: tuple[int, int, int] = (1, 1, 1)  # nights, weekends, holidays
    profiles: tuple[Profile, ...] = PROFILES


@dataclass(frozen=True)
class Metrics:
    """What a variant achieves."""

    wishes_total: int
    wishes_granted: int
    important_total: int
    important_granted: int
    burden_spread: int
    burden_min: int
    burden_max: int
    overtime_hours: float
    isolated_nights: int
    changes_from_prior: int
    hours_ratio: dict[str, float]  # per person: planned + leave credit over contract hours

    @property
    def wish_rate(self) -> float:
        """Return the share of wishes granted."""
        return self.wishes_granted / self.wishes_total if self.wishes_total else 1.0

    @property
    def important_rate(self) -> float:
        """Return the share of important wishes granted."""
        return self.important_granted / self.important_total if self.important_total else 1.0


@dataclass(frozen=True)
class Variant:
    """One complete roster proposal."""

    label: str
    profile: str
    assignments: tuple[tuple[str, date, str], ...]
    metrics: Metrics
    status: str  # OPTIMAL | FEASIBLE
    objective: float
    deterministic_time: float
    wall_seconds: float


@dataclass(frozen=True)
class Explanation:
    """Why no valid roster exists: an i18n key with parameters."""

    key: str
    params: dict[str, Any]


@dataclass(frozen=True)
class Result:
    """The outcome of a run."""

    status: str  # ok | infeasible | unknown
    variants: tuple[Variant, ...] = ()
    explanations: tuple[Explanation, ...] = ()
    solver_version: str = ""
    config: dict[str, Any] = field(default_factory=dict)
