"""The synthetic rulebook says what the seeded rule set says (it cannot drift from the data)."""

import json
import re
from pathlib import Path

import polars as pl

from dienstpilot_agents.rag.corpus import CORPUS_DIR


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


def test_the_rule_summary_numbers_match_rule_set_2026_1(seed_dir: Path) -> None:
    rows = pl.read_parquet(seed_dir / "organization" / "rule_set.parquet").to_dicts()
    rules = json.loads(next(r for r in rows if r["version"] == "2026-1")["rules"])
    for name in ("regeln.de.md", "regeln.en.md"):
        body = (CORPUS_DIR / name).read_text(encoding="utf-8")
        assert "2026-1" in body
        for key in (
            "min_rest_hours",
            "max_consecutive_nights",
            "max_weekends_per_month",
            "max_on_call_per_month",
            "max_on_call_home_per_month",
            "bereitschaft_credited_hours",
        ):
            assert f"{int(rules[key])}" in _numbers(body), f"{name}: {key}={rules[key]}"
            assert key in body, f"{name} must name the rule {key}"
        low, high = rules["contract_hours_band"]
        assert {str(round(low * 100)), str(round(high * 100))} <= _numbers(body)
        assert "free_day_after_on_call" in body and rules["free_day_after_on_call"] is True
