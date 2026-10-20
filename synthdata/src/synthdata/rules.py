"""Rule sets as data (ARCHITECTURE §8: rules are typed, declarative records).

The values are assumptions for the fictional department (see ASSUMPTIONS.md).
"""

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RuleSet:
    """One versioned rule set."""

    version: str
    effective_from: date
    min_rest_hours: float
    max_consecutive_nights: int
    max_weekends_per_month: int
    max_on_call_per_month: int  # Bereitschaftsdienst
    max_on_call_home_per_month: int  # Rufbereitschaft
    free_day_after_on_call: bool
    contract_hours_band: tuple[float, float]  # share of monthly contract hours
    contract_hours_band_min_days: int  # band applies only with at least this many rostered workdays
    bereitschaft_credited_hours: float  # "Anrechnung" of a 24 h Bereitschaftsdienst
    change_note_de: str
    change_note_en: str

    def as_json(self) -> dict[str, Any]:
        """Return the rules as a JSON-ready dict (stored in organization.rule_set.rules)."""
        d = asdict(self)
        for k in ("version", "effective_from", "change_note_de", "change_note_en"):
            d.pop(k)
        d["contract_hours_band"] = list(self.contract_hours_band)
        d["qualification_mix"] = {
            "nacht": {"all": "nachtdienstfaehig"},
            "bereitschaft": {"all": "nachtdienstfaehig", "at_least_one": "facharzt"},
            "ruf": {"all": "oberarzt"},
        }
        return d


RULE_SETS: list[RuleSet] = [
    RuleSet(
        version="2021-1",
        effective_from=date(2021, 1, 1),
        min_rest_hours=11.0,
        max_consecutive_nights=4,
        max_weekends_per_month=2,
        max_on_call_per_month=4,
        max_on_call_home_per_month=10,
        free_day_after_on_call=True,
        contract_hours_band=(0.80, 1.10),
        contract_hours_band_min_days=5,
        bereitschaft_credited_hours=18.0,
        change_note_de="Erste Regelversion der Abteilung.",
        change_note_en="First rule version of the department.",
    ),
    RuleSet(
        version="2026-1",
        effective_from=date(2026, 1, 1),
        min_rest_hours=11.0,
        max_consecutive_nights=3,
        max_weekends_per_month=2,
        max_on_call_per_month=4,
        max_on_call_home_per_month=10,
        free_day_after_on_call=True,
        contract_hours_band=(0.80, 1.10),
        contract_hours_band_min_days=5,
        bereitschaft_credited_hours=18.0,
        change_note_de="Höchstens drei Nachtdienste in Folge statt vier (Dienstvereinbarung 2026).",
        change_note_en=(
            "At most three consecutive night shifts instead of four (2026 works agreement)."
        ),
    ),
]


def rules_for(d: date) -> RuleSet:
    """Return the rule set in effect on a date."""
    return max((r for r in RULE_SETS if r.effective_from <= d), key=lambda r: r.effective_from)
