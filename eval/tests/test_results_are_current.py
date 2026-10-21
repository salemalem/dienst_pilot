"""The committed eval results belong to the code in this commit (no stale numbers in docs or W13)."""

import json
from dataclasses import asdict
from pathlib import Path

from dienstpilot_solver.model import PROFILES
from dienstpilot_solver.solve import VERSION as SOLVER_VERSION
from dienstpilot_validator import VERSION as VALIDATOR_VERSION

RESULTS = Path(__file__).resolve().parents[1] / "results"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_balanced_profile_uses_the_tuned_weights() -> None:
    chosen = _load("tuning.json")["chosen"]
    assert asdict(next(p for p in PROFILES if p.name == "balanced")) == chosen


def test_benchmark_results_match_the_solver_and_its_profiles() -> None:
    for name in ("benchmark.json", "benchmark_smoke.json"):
        doc = _load(name)
        assert doc["versions"] == {"solver": SOLVER_VERSION, "validator": VALIDATOR_VERSION}, name
        assert doc["config"]["profiles"] == [asdict(p) for p in PROFILES], name
    c1 = _load("c1.json")
    assert c1["results_sha256"] == _load("benchmark.json")["results_sha256"]


def test_validator_results_match_the_validator() -> None:
    assert _load("c2.json")["validator_version"] == VALIDATOR_VERSION
    assert _load("tuning.json")["solver_version"] == SOLVER_VERSION
