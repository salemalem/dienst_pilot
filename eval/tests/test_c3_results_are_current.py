"""The committed C3 result belongs to the C3 code, the rule file and the served bundle."""

import json
from pathlib import Path

from dienstpilot_eval.c3_versions import CHAMPION_DIR, RULE, ml_sources_sha256, sha256_file
from dienstpilot_ml.absence_forecast.models import bundle_sha256

RESULT = Path(__file__).resolve().parents[1] / "results" / "c3.json"


def _doc() -> dict:  # type: ignore[type-arg]
    return json.loads(RESULT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_committed_bundle_hash_matches_the_result() -> None:
    assert bundle_sha256(CHAMPION_DIR) == _doc()["champion"]["bundle_sha256"]


def test_the_result_was_made_by_this_code_and_this_rule() -> None:
    code = _doc()["versions"]["code"]
    assert code["ml_sources_sha256"] == ml_sources_sha256(), "re-run make eval"
    assert code["promotion_rule_sha256"] == sha256_file(RULE), "the rule changed after the run"


def test_the_champion_follows_the_pre_registered_rule() -> None:
    doc = _doc()
    checks = doc["promotion"]["checks"]
    promoted = all(c["passed"] for c in checks.values())
    assert doc["champion"]["promoted_challenger"] is promoted
    expected = "lightgbm" if promoted else doc["champion"]["best_baseline_by_cv"]
    assert doc["champion"]["kind"] == expected
    cv = doc["cv_2022_2024"]
    baselines = {k: v["mean_poisson_deviance"] for k, v in cv.items() if k != "lightgbm"}
    assert doc["champion"]["best_baseline_by_cv"] == min(baselines, key=baselines.__getitem__)


def test_the_test_period_is_2025_only() -> None:
    split = _doc()["split"]
    assert split["test"].startswith("2025") and split["train_and_cv"].endswith(
        "2024-12-31, rolling origin, 6 expanding folds"
    )
