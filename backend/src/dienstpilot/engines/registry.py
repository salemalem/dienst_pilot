"""Which implementation serves each port. Swapping a stand-in for a real engine happens here."""

from dataclasses import dataclass

from dienstpilot.engines.built import CpSatOptimizer, RuleValidator
from dienstpilot.engines.c3 import C3Forecaster
from dienstpilot.engines.c4 import C4PreferenceLearner
from dienstpilot.engines.c5 import C5CoverRanker
from dienstpilot.engines.c6 import C6LeaveFeasibility
from dienstpilot.engines.c7 import build_intake
from dienstpilot.engines.c8 import C8Copilot, build_copilot
from dienstpilot.shared.ports import (
    AbsenceForecaster,
    CoverRanker,
    EngineInfo,
    IntakeParser,
    LeaveFeasibility,
    PreferenceLearner,
    RosterOptimizer,
    Validator,
)
from dienstpilot.shared.settings import get_settings


@dataclass(frozen=True)
class Engines:
    """One implementation per component."""

    optimizer: RosterOptimizer
    validator: Validator
    forecaster: AbsenceForecaster
    preferences: PreferenceLearner
    cover_ranker: CoverRanker
    leave: LeaveFeasibility
    intake: IntakeParser
    copilot: C8Copilot

    def infos(self) -> list[EngineInfo]:
        """Return the descriptions of C1–C8, in order."""
        return [
            e.info
            for e in (
                self.optimizer,
                self.validator,
                self.forecaster,
                self.preferences,
                self.cover_ranker,
                self.leave,
                self.intake,
                self.copilot,
            )
        ]


def default_engines() -> Engines:
    """Return the current set: C1 to C6 built; C7 and C8 as far as their gates let them."""
    return Engines(
        CpSatOptimizer(),
        RuleValidator(),
        C3Forecaster(),
        C4PreferenceLearner(),
        C5CoverRanker(),
        C6LeaveFeasibility(),
        build_intake(get_settings()),
        build_copilot(get_settings()),
    )
