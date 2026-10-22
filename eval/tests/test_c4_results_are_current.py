"""The committed C4 result belongs to the C4 code, the rule file and the served bundle."""

import json
from pathlib import Path

from dienstpilot_eval.c3_versions import C4_CHAMPION_DIR, C4_RULE, c4_sources_sha256, sha256_file
from dienstpilot_ml.preference_learner.models import bundle_sha256

RESULT = Path(__file__).resolve().parents[1] / "results" / "c4.json"


def _doc() -> dict:  # type: ignore[type-arg]
    return json.loads(RESULT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_committed_bundle_hash_matches_the_result() -> None:
    assert bundle_sha256(C4_CHAMPION_DIR) == _doc()["champion"]["bundle_sha256"]


def test_the_result_was_made_by_this_code_and_this_rule() -> None:
    code = _doc()["versions"]["code"]
    assert code["c4_sources_sha256"] == c4_sources_sha256(), "re-run make eval"
    assert code["promotion_rule_sha256"] == sha256_file(C4_RULE), "the rule changed after the run"


def test_the_champion_follows_the_pre_registered_rule() -> None:
    doc = _doc()
    checks = doc["promotion"]["checks"]
    promoted = all(c["passed"] for c in checks.values())
    assert doc["champion"]["promoted_learner"] is promoted
    expected = "hierarchical" if promoted else doc["champion"]["best_baseline_by_cv"]
    assert doc["champion"]["kind"] == expected
    cv = doc["cv_2022_2024"]
    best = max(("pooled", "raw"), key=lambda k: cv[k]["mean_total_ll"])
    assert doc["champion"]["best_baseline_by_cv"] == best
    assert sorted(checks) == sorted(
        f"{p}_{c}"
        for p in ("wish", "avoid")
        for c in ("ll_margin", "bootstrap_ci_excludes_zero", "little_history_not_below_pooled")
    )


def test_the_test_period_is_2025_only() -> None:
    split = _doc()["split"]
    assert split["test"].startswith("2025")
    assert "2024-12-31" in split["train_and_cv"]
