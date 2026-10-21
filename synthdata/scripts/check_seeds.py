"""Generate several seeds and check every published month with the independent checker.

Usage: uv run python synthdata/scripts/check_seeds.py [SEED ...]
Exits non-zero if a seed fails to generate, a published month breaks a rule other than
coverage, or the checker's coverage gaps differ from the generator's recorded ones.
"""

import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from hard_rules import check_all

DEFAULT_SEEDS = [20261020, 20261021, 1, 2, 3, 42, 7, 99, 2024]


def check_seed(seed: int) -> tuple[bool, str]:
    """Generate one seed into a temporary folder and check it."""
    out = Path(tempfile.mkdtemp()) / "v1"
    gen = subprocess.run(
        [sys.executable, "-m", "synthdata", "generate", "--seed", str(seed), "--out", str(out)],
        capture_output=True,
        text=True,
    )
    if gen.returncode:
        return False, "generator refused: " + gen.stderr.strip().splitlines()[-1][:200]
    problems = check_all(out)
    rules = Counter(p.rule for ps in problems.values() for p in ps)
    found = {(p.day, p.detail) for ps in problems.values() for p in ps if p.rule == "coverage"}
    truth = pl.read_parquet(out / "_truth" / "published_violations.parquet")
    recorded = {(r["date"], r["detail"].split(":")[0]) for r in truth.iter_rows(named=True)}
    ok = set(rules) <= {"coverage"} and found == recorded
    return (
        ok,
        f"{len(problems)} months, checker {dict(rules)}, gaps match generator: {found == recorded}",
    )


def main(seeds: list[int]) -> int:
    """Check every seed; return 1 if any fails."""
    failed = 0
    for seed in seeds:
        ok, msg = check_seed(seed)
        failed += not ok
        print(f"{seed:>9}  {'ok  ' if ok else 'FAIL'}  {msg}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main([int(s) for s in sys.argv[1:]] or DEFAULT_SEEDS))
