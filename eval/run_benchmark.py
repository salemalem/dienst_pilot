"""Benchmark: the simulated manual planner against C1 on held-out months (ARCHITECTURE §17.1).

Usage:
  uv run python eval/run_benchmark.py            # full: 2025 -> eval/results/benchmark.json, c1.json
  uv run python eval/run_benchmark.py --smoke    # CI: one month, short solves -> eval/results/benchmark_smoke.json

Both rosters of a month get identical inputs. Hard-rule violations are counted by C2 for both.
"""

import argparse
import hashlib
import json
import statistics
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
from dienstpilot_solver.model import Config
from dienstpilot_solver.solve import VERSION as SOLVER_VERSION
from dienstpilot_solver.solve import solve
from dienstpilot_validator import VERSION as VALIDATOR_VERSION
from dienstpilot_validator import Assignment

from dienstpilot_eval.inputs import Data, to_problem
from dienstpilot_eval.metrics import measure

RESULTS = Path(__file__).resolve().parent / "results"
HELD_OUT = [date(2025, m, 1) for m in range(1, 13)]
TUNING = [date(2024, m, 1) for m in range(7, 13)]
RECOMMENDED = "balanced"


def run(root: Path, months: list[date], cfg: Config) -> dict[str, Any]:
    """Return the benchmark document."""
    data = Data(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    breaches = pl.read_parquet(root / "_truth" / "in_month_breaches.parquet")
    per_month = []
    timing = []
    for m in months:
        md = data.month(m)
        baseline = measure(md, md.published)
        result = solve(to_problem(md), cfg)
        if result.status != "ok":
            per_month.append({"month": m.isoformat(), "baseline": asdict(baseline), "c1": None,
                              "c1_status": result.status})
            continue
        chosen = next((v for v in result.variants if v.profile == RECOMMENDED), result.variants[0])
        c1 = measure(md, tuple(Assignment(*a) for a in chosen.assignments))
        month_breaches = breaches.filter(pl.col("date").dt.strftime("%Y-%m") == m.strftime("%Y-%m"))
        per_month.append({
            "month": m.isoformat(),
            "baseline": asdict(baseline),
            "baseline_in_month_violations": month_breaches.height,
            "c1": asdict(c1),
            "c1_variant": {"label": chosen.label, "profile": chosen.profile, "status": chosen.status},
            "c1_variants": len(result.variants),
        })
        timing.append({"month": m.isoformat(), "wall_seconds": [v.wall_seconds for v in result.variants]})

    def total(side: str, key: str) -> float:
        return sum(p[side][key] for p in per_month if p.get(side))

    def rate(side: str, num: str, den: str) -> float:
        d = total(side, den)
        return round(total(side, num) / d, 4) if d else 0.0

    summary = {
        side: {
            "hard_violations": int(total(side, "hard_violations")),
            "wishes_granted_rate": rate(side, "wishes_granted", "wishes_total"),
            "important_wishes_granted_rate": rate(side, "important_granted", "important_total"),
            "burden_spread_mean": round(statistics.mean(p[side]["burden_spread"] for p in per_month if p.get(side)), 2),
            "overtime_hours": round(total(side, "overtime_hours"), 2),
            "isolated_nights": int(total(side, "isolated_nights")),
        }
        for side in ("baseline", "c1")
    }
    summary["baseline"]["in_month_violations"] = sum(p.get("baseline_in_month_violations", 0) for p in per_month)
    walls = [w for t in timing for w in t["wall_seconds"]]
    doc: dict[str, Any] = {
        "description": "Manual-planner baseline vs C1 (recommended variant) on held-out months of the synthetic data.",
        "dataset": {"seed": manifest["seed"], "generator_version": manifest["generator_version"]},
        "versions": {"solver": SOLVER_VERSION, "validator": VALIDATOR_VERSION},
        "config": {"deterministic_time_per_variant": cfg.deterministic_time, "workers": cfg.workers,
                   "seed": cfg.seed, "variants": cfg.variants, "recommended_profile": RECOMMENDED,
                   "profiles": [asdict(p) for p in cfg.profiles]},
        "held_out_months": [m.isoformat() for m in months],
        "tuning_months": [m.isoformat() for m in TUNING],
        "limitations": [
            "Each month is compared independently from the same as-worked history (the manual roster and its "
            "in-month changes); C1's months are not chained into a year.",
            "In-month violations exist only for the baseline and follow from a simulation parameter "
            "(manual_rule_check_rate, synthdata ASSUMPTIONS.md §13); they are not a finding about real planners.",
            "Synthetic data of a fictional department; no real hospital.",
        ],
        "summary": summary,
        "per_month": per_month,
    }
    doc["results_sha256"] = hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()
    doc["timing"] = {
        "note": "Wall-clock seconds per variant on the machine that ran the benchmark; not reproducible.",
        "median_seconds_per_variant": round(statistics.median(walls), 2) if walls else None,
        "max_seconds_per_variant": round(max(walls), 2) if walls else None,
        "per_month": timing,
    }
    return doc


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/synthetic/v1"))
    ap.add_argument("--smoke", action="store_true", help="one month, short solves")
    args = ap.parse_args(argv)
    if args.smoke:
        doc = run(args.data, [date(2025, 3, 1)], Config(deterministic_time=3.0))
        out = RESULTS / "benchmark_smoke.json"
    else:
        doc = run(args.data, HELD_OUT, Config(deterministic_time=20.0))
        out = RESULTS / "benchmark.json"
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    if not args.smoke:  # the summary the transparency screen (W13) shows for C1
        c1 = {
            "component": "C1",
            "source": "eval/results/benchmark.json",
            "results_sha256": doc["results_sha256"],
            "solver_version": SOLVER_VERSION,
            "held_out_months": f"{doc['held_out_months'][0]}..{doc['held_out_months'][-1]}",
            "summary": doc["summary"],
            "median_seconds_per_variant": doc["timing"]["median_seconds_per_variant"],
            "limitations": doc["limitations"],
        }
        (RESULTS / "c1.json").write_text(json.dumps(c1, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(doc['per_month'])} months)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
