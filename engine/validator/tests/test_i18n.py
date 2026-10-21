import json
from pathlib import Path

from dienstpilot_validator import RULE_KEYS

CATALOG = Path(__file__).resolve().parents[3] / "packages" / "i18n"


def test_every_rule_has_a_message_and_a_fix_in_german_and_english() -> None:
    for lang in ("de", "en"):
        cat = json.loads((CATALOG / f"{lang}.json").read_text(encoding="utf-8"))
        for rule in RULE_KEYS:
            assert cat["violation"].get(rule), (lang, "violation", rule)
            assert cat["fix"].get(rule), (lang, "fix", rule)
        assert {"coverage", "person", "unknown"} <= set(cat["infeasible"])
