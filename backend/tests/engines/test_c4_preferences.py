"""The C4 adapter: bundle identity, suggestion policy, no state between calls."""

import json
from datetime import date, timedelta

from dienstpilot.engines.c4 import BUNDLE_DIR, RESULT, C4PreferenceLearner
from dienstpilot.shared.ports import PreferenceContext
from dienstpilot_ml.preference_learner.models import bundle_sha256

MONDAYS = [date(2025, 1, 6) + timedelta(days=7 * i) for i in range(30)]
CONTEXT = PreferenceContext(
    answered_months=[date(2025, m, 1) for m in range(1, 7)],
    unavailable_days=[],
    assigned=[(d, "spaet") for d in MONDAYS],
)


def test_the_committed_bundle_is_the_one_the_eval_result_describes() -> None:
    doc = json.loads(RESULT.read_text(encoding="utf-8"))
    assert bundle_sha256(BUNDLE_DIR) == doc["champion"]["bundle_sha256"]
    info = C4PreferenceLearner().info
    assert info.implementation == "built" and info.component == "C4"
    assert doc["champion"]["kind"] in info.version


def test_a_person_who_swaps_away_one_cell_often_gets_a_suggestion_with_the_numbers() -> None:
    swapped = [(d, "spaet") for d in MONDAYS[:6]]  # six of thirty Monday late shifts
    found = C4PreferenceLearner().suggest([], swapped, CONTEXT)
    avoid = [s for s in found if s.kind == "avoid"]
    assert [(s.weekday, s.shift_type, s.evidence, s.trials) for s in avoid] == [(0, "spaet", 6, 30)]
    assert avoid[0].rate > avoid[0].department_rate and avoid[0].probability >= 0.8


def test_a_person_without_history_gets_no_suggestions() -> None:
    empty = PreferenceContext([], [], [])
    assert C4PreferenceLearner().suggest([], [], empty) == []


def test_suggestions_do_not_depend_on_earlier_calls() -> None:
    c4 = C4PreferenceLearner()
    swapped = [(d, "spaet") for d in MONDAYS[:6]]
    first = c4.suggest([], swapped, CONTEXT)
    c4.suggest([(MONDAYS[0], "nacht")] * 5, [], CONTEXT)  # somebody else's history in between
    assert c4.suggest([], swapped, CONTEXT) == first
