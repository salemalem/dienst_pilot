"""Evaluate the validator (C2) against the independent Phase 2 checker, and its speed.

Usage:
  uv run python eval/run_validator_eval.py      # -> eval/results/c2.json

1. Every published month: C2 and synthdata/tests/hard_rules.py must report the same findings.
2. Random changes (seeded): add and remove up to four assignments in a month; both must agree.
3. Latency of a full-month validation (wall clock; reported separately, not reproducible).
"""

import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import sys
import time
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from dienstpilot_validator import VERSION, Assignment, MonthInput, validate

from dienstpilot_eval.compare import from_checker, from_validator
from dienstpilot_eval.inputs import Data, month_end

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "eval" / "results"
CHANGE_MONTHS = [date(2024, 3, 1), date(2025, 7, 1), date(2025, 12, 1), date(2026, 10, 1), date(2026, 11, 1)]
CHANGES = 300
SHIFTS = ("frueh", "spaet", "nacht", "bereitschaft", "ruf")


def _checker() -> ModuleType:
    path = REPO / "synthdata" / "tests" / "hard_rules.py"
    spec = importlib.util.spec_from_file_location("hard_rules", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["hard_rules"] = module
    spec.loader.exec_module(module)
    return module


def _days(m: date) -> list[date]:
    return [m + timedelta(days=i) for i in range((month_end(m) - m).days + 1)]


def _random_change(rng: random.Random, inp: MonthInput) -> MonthInput:
    m = inp.month
    in_month = sorted((a for a in inp.assignments if a.day >= m), key=lambda a: (a.day, a.staff_id, a.shift_type))
    staff = sorted({a.staff_id for a in in_month})
    removes = set(rng.sample(in_month, rng.randint(0, 4)))
    adds = [Assignment(rng.choice(staff), rng.choice(_days(m)), rng.choice(SHIFTS)) for _ in range(rng.randint(0, 4))]
    return replace(inp, assignments=tuple(a for a in inp.assignments if a not in removes) + tuple(adds))


def run(root: Path) -> dict[str, Any]:
    """Return the evaluation document."""
    data = Data(root)
    checker = _checker()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    months = sorted(data.published_at)
    agree, found, latencies = 0, 0, []
    by_rule: dict[str, int] = {}
    disagreeing = []
    ds = checker.Dataset(root)
    inputs = {}
    for m in months:
        inp = data.month(m).month
        inputs[m] = inp
        vs = validate(inp)
        for _ in range(5):
            t = time.perf_counter()
            validate(inp)
            latencies.append(time.perf_counter() - t)
        found += len(vs)
        for v in vs:
            by_rule[v.rule] = by_rule.get(v.rule, 0) + 1
        if from_validator(vs) == from_checker(checker.check_month(ds, m)):
            agree += 1
        else:
            disagreeing.append(m.isoformat())
    rng = random.Random(20261020)
    change_agree = 0
    changed_findings = 0
    for i in range(CHANGES):
        m = CHANGE_MONTHS[i % len(CHANGE_MONTHS)]
        mutated = _random_change(rng, inputs[m])
        original = ds.plan[m]
        ds.plan[m] = [(a.staff_id, a.day, a.shift_type) for a in mutated.assignments if a.day >= m]
        mine = from_validator(validate(mutated))
        changed_findings += sum(mine.values())
        change_agree += mine == from_checker(checker.check_month(ds, m))
        ds.plan[m] = original
    latencies.sort()
    doc: dict[str, Any] = {
        "description": "C2 against the independent Phase 2 checker on the synthetic data.",
        "component": "C2",
        "validator_version": VERSION,
        "dataset": {"seed": manifest["seed"], "generator_version": manifest["generator_version"]},
        "published_months": {
            "compared": len(months),
            "agreeing": agree,
            "disagreeing": disagreeing,
            "violations_found": found,
            "violations_by_rule": dict(sorted(by_rule.items())),
            "note": "Violations in published months are the simulated manual planner's in-month "
            "changes (a simulation parameter, synthdata ASSUMPTIONS §13).",
        },
        "random_changes": {
            "months": [m.isoformat() for m in CHANGE_MONTHS],
            "changes": CHANGES,
            "agreeing": change_agree,
            "violations_found": changed_findings,
            "seed": 20261020,
        },
        "summary": {
            "agreement_published_months": f"{agree}/{len(months)}",
            "agreement_random_changes": f"{change_agree}/{CHANGES}",
        },
    }
    doc["results_sha256"] = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
    doc["timing"] = {
        "note": "Wall-clock milliseconds for validating a whole month on the machine that ran this; "
        "not reproducible.",
        "runs": len(latencies),
        "p50_ms": round(1000 * statistics.median(latencies), 2),
        "p95_ms": round(1000 * latencies[int(0.95 * (len(latencies) - 1))], 2),
    }
    return doc


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/synthetic/v1"))
    args = ap.parse_args(argv)
    doc = run(args.data)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "c2.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {doc['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
