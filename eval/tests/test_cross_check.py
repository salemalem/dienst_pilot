"""C2 and the Phase 2 checker are two independent implementations of the same rules.

They must agree exactly on every published month, on November 2026, and on mutated rosters.
"""

from datetime import date
from types import ModuleType

from dienstpilot_validator import validate

from dienstpilot_eval.inputs import Data

from dienstpilot_eval.compare import from_checker, from_validator


def test_validator_and_checker_agree_on_every_published_month(data: Data, checker: ModuleType) -> None:
    ds = checker.Dataset(data.root)
    disagreements = {}
    months = sorted(data.published_at)
    assert len(months) == 71
    for m in months:
        mine = from_validator(validate(data.month(m).month))
        theirs = from_checker(checker.check_month(ds, m))
        if mine != theirs:
            disagreements[m] = (mine - theirs, theirs - mine)
    assert disagreements == {}


def test_november_2026_is_clean_for_both(data: Data, checker: ModuleType) -> None:
    m = date(2026, 11, 1)
    assert validate(data.month(m).month) == []
    assert checker.check_month(checker.Dataset(data.root), m) == []
