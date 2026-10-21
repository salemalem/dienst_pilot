"""Which implementation serves each port. Swapping a stand-in for a real engine happens here."""

from dataclasses import dataclass

from dienstpilot.engines.built import CpSatOptimizer, RuleValidator
from dienstpilot.engines.standins import (
    CopilotStandIn,
    CoverRankStandIn,
    ForecastStandIn,
    IntakeStandIn,
    LeaveFeasibilityStandIn,
    PreferenceStandIn,
)
from dienstpilot.shared.ports import (
    AbsenceForecaster,
    Copilot,
    CoverRanker,
    EngineInfo,
    IntakeParser,
    LeaveFeasibility,
    PreferenceLearner,
    RosterOptimizer,
    Validator,
)


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
    copilot: Copilot

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
    """Return the current set: C1 and C2 built, stand-ins for C3–C8."""
    return Engines(
        CpSatOptimizer(),
        RuleValidator(),
        ForecastStandIn(),
        PreferenceStandIn(),
        CoverRankStandIn(),
        LeaveFeasibilityStandIn(),
        IntakeStandIn(),
        CopilotStandIn(),
    )
