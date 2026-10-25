"""Tune the weights of C1's recommended profile ("balanced") on the tuning months only.

Usage:
  uv run python eval/tune_profiles.py      # -> eval/results/tuning.json

The tuning months (July–December 2024) come before the held-out year 2025, so the benchmark
never sees data the weights were chosen on. The criterion is fixed before the run:

  1. Every candidate's roster must pass C2 (a candidate with a violation is out).
  2. Rank the candidates on each of four totals over the tuning months: share of wishes granted
     (higher is better), share of important wishes granted (higher), mean burden spread (lower),
     overtime hours (lower). The lowest rank sum wins; a tie keeps the earlier candidate.

The grid is fixed: wishes {4, 6, 8} × spread {5, 8, 12} × overtime {3, 6}, with isolated nights 2
and stability 1, starting with the design weights (6, 8, 3). The winner goes into
``dienstpilot_solver.model.PROFILES``; a test checks that the two agree.

The other two profiles (wishes_first, zero_overtime) are deliberate extremes for the Planner to
compare against and are not tuned.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Any

from dienstpilot_solver.model import PROFILES, Config, Profile
from dienstpilot_solver.solve import VERSION as SOLVER_VERSION
from dienstpilot_solver.solve import solve
from dienstpilot_validator import Assignment

from dienstpilot_eval.inputs import Data, to_problem
from dienstpilot_eval.metrics import measure

RESULTS = Path(__file__).resolve().parent / "results"
TUNING = [date(2024, m, 1) for m in range(7, 13)]
DESIGN = Profile("balanced", wishes=6, spread=8, overtime=3, isolated_nights=2, stability=1)
CANDIDATES = [DESIGN] + [
    Profile("balanced", wishes=w, spread=s, overtime=o, isolated_nights=2, stability=1)
    for w in (4, 6, 8)
    for s in (5, 8, 12)
    for o in (3, 6)
    if (w, s, o) != (6, 8, 3)
]
METRICS = (  # (name, higher is better)
    ("wishes_granted_rate", True),
    ("important_wishes_granted_rate", True),
    ("burden_spread_mean", False),
    ("overtime_hours", False),
)


def evaluate(data: Data, profile: Profile, cfg: Config) -> dict[str, Any]:
    """Return the totals of one candidate over the tuning months."""
    totals = {
        "wishes_total": 0,
        "wishes_granted": 0,
        "important_total": 0,
        "important_granted": 0,
        "overtime_hours": 0.0,
        "hard_violations": 0,
    }
    spreads, statuses = [], []
    for m in TUNING:
        md = data.month(m)
        result = solve(to_problem(md), replace(cfg, variants=1, profiles=(profile,)))
        if result.status != "ok":
            statuses.append(result.status)
            totals["hard_violations"] += 1  # no roster counts as failing the month
            continue
        v = result.variants[0]
        statuses.append(v.status)
        r = measure(md, tuple(Assignment(*a) for a in v.assignments))
        for k in (
            "wishes_total",
            "wishes_granted",
            "important_total",
            "important_granted",
            "hard_violations",
        ):
            totals[k] += getattr(r, k)
        totals["overtime_hours"] += r.overtime_hours
        spreads.append(r.burden_spread)
    return {
        "profile": asdict(profile),
        "statuses": statuses,
        "hard_violations": totals["hard_violations"],
        "wishes_granted_rate": round(totals["wishes_granted"] / totals["wishes_total"], 4)
        if totals["wishes_total"]
        else 1.0,
        "important_wishes_granted_rate": round(
            totals["important_granted"] / totals["important_total"], 4
        )
        if totals["important_total"]
        else 1.0,
        "burden_spread_mean": round(sum(spreads) / len(spreads), 3) if spreads else None,
        "overtime_hours": round(totals["overtime_hours"], 2),
    }


def choose(rows: list[dict[str, Any]]) -> int:
    """Return the index of the winner under the criterion in the module docstring."""
    valid = [i for i, r in enumerate(rows) if r["hard_violations"] == 0]
    sums = {i: 0 for i in valid}
    for name, higher in METRICS:
        ordered = sorted({rows[i][name] for i in valid}, reverse=higher)
        for i in valid:
            sums[i] += ordered.index(rows[i][name]) + 1  # equal values share a rank
            rows[i].setdefault("ranks", {})[name] = ordered.index(rows[i][name]) + 1
    for i in valid:
        rows[i]["rank_sum"] = sums[i]
    return min(valid, key=lambda i: (sums[i], i))


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/synthetic/v1"))
    args = ap.parse_args(argv)
    data = Data(args.data)
    manifest = json.loads((args.data / "manifest.json").read_text(encoding="utf-8"))
    cfg = Config(deterministic_time=20.0)
    rows = [evaluate(data, p, cfg) for p in CANDIDATES]
    winner = choose(rows)
    doc: dict[str, Any] = {
        "description": "Weights of C1's recommended profile, chosen on the tuning months only.",
        "dataset": {"seed": manifest["seed"], "generator_version": manifest["generator_version"]},
        "solver_version": SOLVER_VERSION,
        "tuning_months": [m.isoformat() for m in TUNING],
        "criterion": "C2-valid in every month; lowest rank sum over wishes granted, important wishes "
        "granted, mean burden spread and overtime hours; a tie keeps the earlier candidate "
        "(the design weights 6/8/3 are first).",
        "grid": "wishes {4,6,8} x spread {5,8,12} x overtime {3,6}; isolated_nights 2, stability 1",
        "deterministic_time_per_month": cfg.deterministic_time,
        "candidates": rows,
        "chosen": rows[winner]["profile"],
        "differs_from_design_weights": rows[winner]["profile"] != asdict(DESIGN),
    }
    doc["results_sha256"] = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "tuning.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    current = asdict(next(p for p in PROFILES if p.name == "balanced"))
    note = (
        "matches PROFILES"
        if current == doc["chosen"]
        else "UPDATE PROFILES in dienstpilot_solver.model"
    )
    print(f"wrote {out}: chosen {doc['chosen']} ({note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
