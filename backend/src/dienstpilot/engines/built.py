"""C1 and C2: adapters for the engine packages engine/solver and engine/validator."""

from dienstpilot.shared.ports import EngineInfo, RosterOptimizer, Validator
from dienstpilot_solver.model import Config, Problem, Result
from dienstpilot_solver.solve import VERSION as SOLVER_VERSION
from dienstpilot_solver.solve import solve
from dienstpilot_validator import VERSION as VALIDATOR_VERSION
from dienstpilot_validator import Assignment, MonthInput, Violation, validate, validate_change

C1_INFO = EngineInfo(
    "C1",
    "built",
    SOLVER_VERSION,
    "OR-Tools CP-SAT: hard rules as constraints, weighted soft objectives, 2-3 variants.",
    None,
)
C2_INFO = EngineInfo(
    "C2",
    "built",
    VALIDATOR_VERSION,
    "Independent rule checker on the declarative rule set; cross-checked against a second "
    "implementation.",
    None,
)


class CpSatOptimizer(RosterOptimizer):
    """C1 on CP-SAT."""

    info = C1_INFO

    def solve(self, problem: Problem, config: Config) -> Result:
        """Solve the month."""
        return solve(problem, config)


class RuleValidator(Validator):
    """C2."""

    info = C2_INFO

    def validate(self, month: MonthInput) -> list[Violation]:
        """Validate a whole month."""
        return validate(month)

    def validate_change(
        self, month: MonthInput, remove: list[Assignment], add: list[Assignment]
    ) -> tuple[list[Violation], list[Violation]]:
        """Validate a change to a month."""
        return validate_change(month, remove, add)
