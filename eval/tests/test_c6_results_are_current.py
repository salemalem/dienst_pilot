"""The committed C6 result belongs to the C6 code, the rule file, the labels and the served bundle."""

import hashlib
import json
from pathlib import Path

from dienstpilot_eval.c3_versions import C6_CHAMPION_DIR, C6_RULE, c6_sources_sha256, sha256_file
from dienstpilot_ml.leave_surrogate.models import bundle_sha256

RESULT = Path(__file__).resolve().parents[1] / "results" / "c6.json"
LABELS = Path(__file__).resolve().parents[2] / "ml" / "leave_surrogate" / "labels"


def _doc() -> dict:  # type: ignore[type-arg]
    return json.loads(RESULT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_committed_bundle_hash_matches_the_result() -> None:
    assert bundle_sha256(C6_CHAMPION_DIR) == _doc()["champion"]["bundle_sha256"]


def test_the_result_was_made_by_this_code_this_rule_and_these_labels() -> None:
    doc = _doc()
    code = doc["versions"]["code"]
    assert code["c6_sources_sha256"] == c6_sources_sha256(), "re-run make eval"
    assert code["promotion_rule_sha256"] == sha256_file(C6_RULE), "the rule changed after the run"
    for name, sha in doc["labels"]["files_sha256"].items():
        assert hashlib.sha256((LABELS / name).read_bytes()).hexdigest() == sha, name


def test_the_champion_follows_the_pre_registered_rule() -> None:
    doc = _doc()
    checks = doc["promotion"]["checks"]
    assert sorted(checks) == [
        "hint_latency_p95_under_limit",
        "precision_higher_by_margin_and_ci_excludes_zero",
        "recall_at_least_stand_in",
    ]
    promoted = all(c["passed"] for c in checks.values())
    assert doc["champion"]["promoted_learner"] is promoted
    expected = "lightgbm" if promoted else doc["champion"]["best_baseline_by_cv"]
    assert doc["champion"]["kind"] == expected
    cv = doc["cv_2022_2024"]
    best = (
        "logistic"
        if cv["logistic"]["oof_precision"] > cv["stand_in"]["oof_precision"]
        else "stand_in"
    )
    assert doc["champion"]["best_baseline_by_cv"] == best
    p = checks["precision_higher_by_margin_and_ci_excludes_zero"]
    assert p["passed"] == (p["difference"] >= 0.01 and p["difference_95ci"][0] > 0)
    assert checks["hint_latency_p95_under_limit"]["limit_ms"] == 50.0


def test_the_target_follows_the_registered_rule_and_reporting_order_is_natural_first() -> None:
    doc = _doc()
    t = doc["target"]
    binary = t["training_trade_off_share"] < 0.05 or t["training_trade_off_rows"] < 100
    assert (t["kind"] == "binary") == binary
    assert doc["reporting_order"] == ["natural", "stress", "pooled"]
    for kind in ("stand_in", "logistic", "lightgbm"):
        assert {"natural", "stress", "pooled"} <= set(doc["test_2025"][kind])
        assert doc["test_2025"][kind]["pooled_label"].endswith("including simulated stress states")
    assert "pooled including simulated stress states" in doc["agreement_with_solver_2025"]
