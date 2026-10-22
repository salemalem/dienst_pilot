"""Prices from ``eval/pricing.json`` (copied from Anthropic's pricing page, with date and URL)."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dienstpilot_agents.llm.types import LlmError, Usage

PATH = Path(__file__).resolve().parents[4] / "eval" / "pricing.json"


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens for prompts up to the long-context threshold."""

    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float
    batch_input: float
    batch_output: float
    long_context_threshold: int


@lru_cache
def _raw() -> dict[str, object]:
    return json.loads(PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def price(model: str) -> ModelPrice:
    """Return the price of a model, or raise if pricing.json does not list it."""
    models = _raw()["models"]
    assert isinstance(models, dict)
    if model not in models:
        raise LlmError(f"no price for {model} in eval/pricing.json")
    return ModelPrice(**models[model])


def cost_usd(usage: Usage, model: str, *, batch: bool = False, ttl: str = "5m") -> float:
    """Return what a call costs. A prompt over the price threshold is refused (see the note).

    Batch halves input and output; the cache multipliers stack with it, as the pricing page says.
    """
    p = price(model)
    if usage.prompt_tokens > p.long_context_threshold:
        raise LlmError(
            f"a prompt of {usage.prompt_tokens} tokens is over the {p.long_context_threshold} "
            "threshold where the higher price applies; this project keeps prompts below it"
        )
    scale = 0.5 if batch else 1.0
    write = p.cache_write_1h if ttl == "1h" else p.cache_write_5m
    total = (
        usage.input_tokens * (p.batch_input if batch else p.input)
        + usage.output_tokens * (p.batch_output if batch else p.output)
        + usage.cache_write_tokens * write * scale
        + usage.cache_read_tokens * p.cache_read * scale
    )
    return total / 1_000_000
