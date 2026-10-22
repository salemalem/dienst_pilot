"""Spending and cost estimates for the paid LLM calls of Phase 10.

    uv run python eval/cost_model.py report                 # what the ledger says was spent
    uv run python eval/cost_model.py estimate c7            # expected and worst-case cost, no calls

The ledger (eval/usage/ledger.jsonl) is written by every live call; prices come from
eval/pricing.json. The limit is 4.50 US dollars for the whole phase (5 euros is the budget; the
guard stops below it). Estimates are made before a run and shown to the person who pays.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from dienstpilot_agents.intake.prompt import build_request
from dienstpilot_agents.llm.budget import LIMIT_USD, estimate_prompt_tokens, worst_case_usd
from dienstpilot_agents.llm.ledger import Ledger
from dienstpilot_agents.llm.pricing import cost_usd
from dienstpilot_agents.llm.types import Usage

REPO = Path(__file__).resolve().parents[1]
MODEL = "claude-haiku-5-5"
EXPECTED_OUTPUT_TOKENS = 160  # a typical answer: a small JSON object


def report() -> None:
    """Print the ledger by component and purpose and the running total."""
    entries = Ledger().entries()
    by: dict[tuple[str, str, str], list[float]] = defaultdict(lambda: [0, 0, 0, 0, 0.0])  # type: ignore[assignment]
    for e in entries:
        v = by[(e.component, e.purpose, e.mode)]
        v[0] += 1
        v[1] += e.input_tokens + e.cache_write_tokens + e.cache_read_tokens
        v[2] += e.output_tokens
        v[3] += e.cache_read_tokens
        v[4] += e.cost_usd
    print(
        f"{'component':9} {'purpose':8} {'mode':6} {'calls':>6} {'prompt tok':>11} {'out tok':>8} {'cached':>9} {'USD':>9}"
    )
    for (comp, purpose, mode), v in sorted(by.items()):
        print(
            f"{comp:9} {purpose:8} {mode:6} {int(v[0]):6d} {int(v[1]):11d} {int(v[2]):8d} {int(v[3]):9d} {v[4]:9.4f}"
        )
    total = Ledger().total_usd()
    print(f"\nTotal spent: ${total:.4f} of ${LIMIT_USD:.2f}  (left: ${LIMIT_USD - total:.4f})")


def estimate_c7() -> dict[str, dict[str, float]]:
    """Return expected and worst-case dollars of the three C7 runs (nothing is sent)."""
    doc = json.loads((REPO / "eval" / "c7_utterances.json").read_text(encoding="utf-8"))
    reqs = {
        split: [
            build_request(u["text"], doc["month"], u["language"], MODEL)
            for u in doc["utterances"]
            if u["split"] == split
        ]
        for split in ("dev", "test")
    }
    system_tokens = estimate_prompt_tokens(reqs["dev"][0]) - len(str(reqs["dev"][0].messages)) // 2

    def run(rs: list, *, batch: bool, cached_after_first: bool) -> dict[str, float]:  # type: ignore[type-arg]
        total = 0.0
        for i, r in enumerate(rs):
            prompt = estimate_prompt_tokens(r)
            shared = min(system_tokens, prompt)
            first = i == 0 or not cached_after_first
            usage = Usage(
                input_tokens=prompt - shared if cached_after_first else prompt,
                output_tokens=EXPECTED_OUTPUT_TOKENS,
                cache_write_tokens=shared if (cached_after_first and first) else 0,
                cache_read_tokens=shared if (cached_after_first and not first) else 0,
            )
            total += cost_usd(usage, MODEL, batch=batch, ttl="1h" if batch else "5m")
        worst = sum(worst_case_usd(r, batch=batch) for r in rs)
        return {
            "calls": len(rs),
            "expected_usd": round(total, 4),
            "worst_case_usd": round(worst, 4),
        }

    return {
        "dev (60, batch)": run(reqs["dev"], batch=True, cached_after_first=True),
        "latency (30 live, sequential)": run(
            reqs["dev"][:30], batch=False, cached_after_first=True
        ),
        "test (140, batch, once)": run(reqs["test"], batch=True, cached_after_first=True),
    }


def main() -> None:
    """Dispatch."""
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "report":
        report()
    elif cmd == "estimate" and sys.argv[2:3] == ["c7"]:
        est = estimate_c7()
        for name, v in est.items():
            print(
                f"{name:32} {int(v['calls']):4d} calls  expected ${v['expected_usd']:.4f}  worst case ${v['worst_case_usd']:.4f}"
            )
        print(
            f"{'all three':32} expected ${sum(v['expected_usd'] for v in est.values()):.4f}  "
            f"worst case ${sum(v['worst_case_usd'] for v in est.values()):.4f}  "
            f"(spent so far ${Ledger().total_usd():.4f}, limit ${LIMIT_USD:.2f})"
        )
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
