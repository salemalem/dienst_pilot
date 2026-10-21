"""Fixed facts of the simulated world: period, demo date, department, tunable parameters."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")

DEFAULT_SEED = 20261020

HISTORY_START = date(2021, 1, 1)
HISTORY_END = date(2025, 12, 31)
DEMO_START = date(2026, 1, 1)
DEMO_END = date(2026, 12, 31)

# UI_SPEC §1: Tuesday, 20 October 2026. Nothing in the dataset happens after this moment.
DEMO_NOW = datetime(2026, 10, 20, 6, 0, tzinfo=TZ)
# Last roster month that is planned and published; December 2026 is the open request window.
LAST_PUBLISHED_MONTH = date(2026, 11, 1)
OPEN_WINDOW_MONTH = date(2026, 12, 1)
OPEN_WINDOW_RESPONDENTS = 21

DEPARTMENT_NAME = "Klinik für Innere Medizin, Klinikum Musterstadt"
DEPARTMENT_SHORT = "Innere Medizin"


@dataclass(frozen=True)
class Params:
    """Simulation parameters. All are assumptions (see ASSUMPTIONS.md), not findings."""

    # Sickness: base daily hazard of a new episode per person, mean extra days after day one.
    sick_base_hazard: float = 0.0075
    sick_mean_extra_days: float = 2.6
    sick_max_days: int = 21
    post_night_hazard_factor: float = 1.4
    post_night_days: int = 3
    # Manual era: share of in-month changes (cover, swaps) the planner checks against the rules.
    manual_rule_check_rate: float = 0.85
    # Manual planner: probability that a submitted wish is read at all, and an important one.
    planner_reads_wish: float = 0.75
    planner_reads_important_wish: float = 0.9
    # Request windows: mean probability that a person responds.
    response_rate: float = 0.86
    # Leave: entitlement and concurrency limits used by the planner when deciding.
    leave_days_per_year: int = 30
    # Target share of first leave requests the planner declines. PLACEHOLDER, to be confirmed
    # with a physician; the generator calibrates holiday clustering to approach it.
    target_first_request_decline_rate: float = 0.15
    max_concurrent_leave: int = 6
    max_concurrent_senior_leave: int = 2
    # Cover: maximum colleagues asked before the planner escalates.
    max_cover_asks: int = 6
    planner_attempts_history: int = 12
    planner_attempts_demo: int = 300


PARAMS = Params()
