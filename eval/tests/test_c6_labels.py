"""The C6 labels: protocol, no identifiers, and a re-solve of a few committed labels."""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from dienstpilot_eval.c6_labels import PER_MONTH, TEST_MONTHS, TRAIN_MONTHS, Spec, specs

LABELS = Path(__file__).resolve().parents[2] / "ml" / "leave_surrogate" / "labels"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
OUTCOMES = {"coverable", "coverable_with_trade_off", "not_coverable"}


def _rows(name: str) -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(x) for x in (LABELS / name).read_text(encoding="utf-8").splitlines()]


def test_the_protocol_has_the_registered_months_and_sizes() -> None:
    assert TRAIN_MONTHS[0] == date(2021, 1, 1) and TRAIN_MONTHS[-1] == date(2024, 12, 1)
    assert TEST_MONTHS[0] == date(2025, 1, 1) and TEST_MONTHS[-1] == date(2025, 12, 1)
    assert len(specs("train")) == 48 * PER_MONTH["train"]
    assert len(specs("test")) == 12 * PER_MONTH["test"]
    # half natural, half stress (alternating index): the registered 50/50
    assert sum(s.index % 2 == 0 for s in specs("train", 62)) == 24 * 62


def test_committed_labels_match_the_seal_and_carry_no_identifier() -> None:
    meta = json.loads((LABELS / "meta.json").read_text(encoding="utf-8"))
    for name, sha in meta["files"].items():
        assert hashlib.sha256((LABELS / name).read_bytes()).hexdigest() == sha, name
    for f in LABELS.glob("*.jsonl"):
        assert not UUID.search(f.read_text(encoding="utf-8")), f"{f.name} holds an identifier"


def test_train_labels_are_2021_2024_and_test_labels_are_2025() -> None:
    assert {r["month"][:4] for r in _rows("train.jsonl")} == {"2021", "2022", "2023", "2024"}
    assert {r["month"][:4] for r in _rows("test.jsonl")} == {"2025"}
    for r in _rows("train.jsonl") + _rows("test.jsonl"):
        assert r["outcome"] in OUTCOMES and r["stratum"] in ("natural", "stress")
        assert (r["stratum"] == "natural") == (r["k_stress"] == 0)


def test_the_ci_sample_is_part_of_the_train_labels() -> None:
    train = {r["id"]: r for r in _rows("train.jsonl")}
    sample = _rows("sample.jsonl")
    assert 20 <= len(sample) <= 60
    assert all(train[r["id"]] == r for r in sample)


def test_a_few_sample_labels_are_reproduced_by_the_solver(seed_root: Path) -> None:
    """The sample's answer is what the M5 decision gives again (workers=2, as when generated)."""
    from dataclasses import replace

    from dienstpilot_eval.c6_labels import CHECK_CONFIG, World, label

    w = World(seed_root)
    cfg = replace(CHECK_CONFIG, workers=2)
    sample = _rows("sample.jsonl")
    pick = [
        next(r for r in sample if r["outcome"] == o)
        for o in OUTCOMES
        if any(r["outcome"] == o for r in sample)
    ]
    for r in pick:
        split, month, idx = r["id"].split("|")
        got = label(w, Spec(split, date.fromisoformat(month), int(idx)), cfg).to_json()
        assert got["outcome"] == r["outcome"] and got["facts"] == r["facts"], r["id"]
