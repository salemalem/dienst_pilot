"""The hard budget: no paid call is sent if the phase total could pass the limit.

The user's limit is 5 euros for all of Phase 10; the guard stops at 4.50 US dollars (the ledger is
in dollars, as the price list is). The check happens before every call with the call's worst
case (every input token uncached, the output at ``max_tokens``), so the limit cannot be passed by
a single call, and again after it, from the ledger.
"""

from dataclasses import dataclass

from dienstpilot_agents.llm.ledger import Ledger
from dienstpilot_agents.llm.pricing import price
from dienstpilot_agents.llm.types import BudgetExceededError, LlmRequest

LIMIT_USD = 4.50
CHARS_PER_TOKEN = 2.5  # deliberately pessimistic (German text and JSON tokenise at about 3.5)
TOOL_OVERHEAD_TOKENS = 406  # Claude Haiku 5.5 with a forced tool (pricing page)


def estimate_prompt_tokens(request: LlmRequest) -> int:
    """Return a pessimistic token count of a request's prompt."""
    chars = len(str(request.canonical()["system"])) + len(str(request.canonical()["messages"]))
    chars += len(str(request.canonical()["tools"]))
    return int(chars / CHARS_PER_TOKEN) + TOOL_OVERHEAD_TOKENS


def worst_case_usd(request: LlmRequest, *, batch: bool = False) -> float:
    """Return the most a request can cost: uncached, and the output at max_tokens."""
    p = price(request.model)
    tokens = estimate_prompt_tokens(request)
    rate_in = (p.batch_input if batch else p.input) / 1_000_000
    rate_out = (p.batch_output if batch else p.output) / 1_000_000
    # A cache write costs more than plain input; allow for the dearest case.
    write = max(p.cache_write_5m, p.cache_write_1h) * (0.5 if batch else 1.0) / 1_000_000
    return tokens * max(rate_in, write) + request.max_tokens * rate_out


@dataclass(frozen=True)
class Budget:
    """The phase budget over a ledger."""

    ledger: Ledger
    limit_usd: float = LIMIT_USD

    def remaining(self) -> float:
        """Return what may still be spent."""
        return self.limit_usd - self.ledger.total_usd()

    def check(self, expected_usd: float, what: str) -> None:
        """Raise if spending ``expected_usd`` more could take the total over the limit."""
        spent = self.ledger.total_usd()
        if spent + expected_usd > self.limit_usd:
            raise BudgetExceededError(
                f"{what}: expected ${expected_usd:.4f} on top of ${spent:.4f} spent would pass the "
                f"${self.limit_usd:.2f} limit"
            )
