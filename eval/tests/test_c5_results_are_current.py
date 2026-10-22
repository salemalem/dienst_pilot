"""The committed C5 result belongs to the C5 code, the rule file and the served bundle."""

import json
from pathlib import Path

from dienstpilot_eval.c3_versions import C5_CHAMPION_DIR, C5_RULE, c5_sources_sha256, sha256_file
from dienstpilot_ml.cover_ranker.models import bundle_sha256

RESULT = Path(__file__).resolve().parents[1] / "results" / "c5.json"


def _doc() -> dict:  # type: ignore[type-arg]
    return json.loads(RESULT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_committed_bundle_hash_matches_the_result() -> None:
    assert bundle_sha256(C5_CHAMPION_DIR) == _doc()["champion"]["bundle_sha256"]


def test_the_result_was_made_by_this_code_and_this_rule() -> None:
    code = _doc()["versions"]["code"]
    assert code["c5_sources_sha256"] == c5_sources_sha256(), "re-run make eval"
    assert code["promotion_rule_sha256"] == sha256_file(C5_RULE), "the rule changed after the run"


def test_the_champion_follows_the_pre_registered_rule() -> None:
    doc = _doc()
    checks = doc["promotion"]["checks"]
    promoted = all(c["passed"] for c in checks.values())
    assert doc["champion"]["promoted_learner"] is promoted
    expected = "lightgbm" if promoted else doc["champion"]["best_baseline_by_cv"]
    assert doc["champion"]["kind"] == expected
    cv = doc["cv_2022_2024"]
    best = min(("base_rate", "logistic"), key=lambda k: cv[k]["mean_brier"])
    assert doc["champion"]["best_baseline_by_cv"] == best
    assert sorted(checks) == [
        "auc_higher_and_at_least_floor",
        "brier_bootstrap_ci_excludes_zero",
        "brier_margin",
        "ece_at_most_ceiling",
    ]


def test_the_test_period_is_2025_only_and_the_replay_has_the_four_policies() -> None:
    doc = _doc()
    assert doc["split"]["test"].startswith("2025")
    assert "2024-12-31" in doc["split"]["train_and_cv"]
    assert sorted(doc["replay_2025"]["policies"]) == [
        "fairness_first_champion",
        "fairness_first_exact_buckets_sensitivity",
        "most_reliable_first",
        "stand_in",
    ]
    assert doc["policy"]["bucket_width_covers_last_90_days"] == 2
