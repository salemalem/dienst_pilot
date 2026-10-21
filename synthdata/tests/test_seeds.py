"""Robustness: other seeds also give clean published rosters (CI job "seeds")."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_seeds.py"
spec = importlib.util.spec_from_file_location("check_seeds", SCRIPT)
assert spec is not None and spec.loader is not None
check_seeds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_seeds)


@pytest.mark.seeds
@pytest.mark.parametrize("seed", check_seeds.DEFAULT_SEEDS)
def test_seed_generates_clean_published_rosters(seed: int) -> None:
    ok, message = check_seeds.check_seed(seed)
    assert ok, message
