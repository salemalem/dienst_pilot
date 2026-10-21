"""C1 and C2 until Phase 7: the ports exist, every call answers "not implemented"."""

from datetime import date
from typing import Any

from dienstpilot.shared.ports import (
    EngineInfo,
    EngineNotImplementedError,
    RosterOptimizer,
    Validator,
)

C1_INFO = EngineInfo("C1", "not_implemented", "-", "CP-SAT roster optimizer; built in phase 7.", 7)
C2_INFO = EngineInfo(
    "C2", "not_implemented", "-", "Independent rule and compliance validator; built in phase 7.", 7
)


class OptimizerNotImplemented(RosterOptimizer):
    """C1 placeholder."""

    info = C1_INFO

    def generate(self, month: date, department_id: str) -> list[dict[str, Any]]:
        """Raise: roster generation arrives in Phase 7."""
        raise EngineNotImplementedError(self.info)


class ValidatorNotImplemented(Validator):
    """C2 placeholder."""

    info = C2_INFO

    def validate(self, month: date, assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Raise: validation arrives in Phase 7."""
        raise EngineNotImplementedError(self.info)
