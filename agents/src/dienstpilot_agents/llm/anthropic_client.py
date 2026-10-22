"""The live adapter: the only module that imports the Anthropic SDK.

No extended thinking and no sampling parameters are sent. The system prompt and the tool
definitions are cached (``cache_control`` on the last system block); work nobody waits for goes
through the Batch API at half price. Before every call the budget guard looks at the ledger, and
every answer is written to it.
"""

import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dienstpilot_agents.llm import fixtures
from dienstpilot_agents.llm.budget import Budget, worst_case_usd
from dienstpilot_agents.llm.ledger import Ledger
from dienstpilot_agents.llm.pricing import cost_usd
from dienstpilot_agents.llm.types import (
    LlmError,
    LlmRequest,
    LlmResponse,
    NoApiKeyError,
    Usage,
)

BATCH_POLL_SECONDS = 20.0
BATCH_TTL = "1h"  # the pricing page recommends the 1-hour cache for batches


def _params(request: LlmRequest, ttl: str | None = None) -> dict[str, Any]:
    system: list[dict[str, Any]] = []
    for b in request.system:
        block: dict[str, Any] = {"type": "text", "text": b.text}
        if b.cache:
            block["cache_control"] = {"type": "ephemeral", **({"ttl": ttl} if ttl else {})}
        system.append(block)
    params: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "system": system,
        "messages": list(request.messages),
    }
    if request.tools:
        params["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in request.tools
        ]
    if request.force_tool:
        params["tool_choice"] = {"type": "tool", "name": request.force_tool}
    return params


def _usage(u: Any) -> Usage:
    return Usage(
        input_tokens=int(getattr(u, "input_tokens", 0) or 0),
        output_tokens=int(getattr(u, "output_tokens", 0) or 0),
        cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
        cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
    )


def _response(request: LlmRequest, message: Any, latency: float | None) -> LlmResponse:
    tool_input = None
    text = ""
    for block in message.content:
        if block.type == "tool_use":
            tool_input = dict(block.input)
        elif block.type == "text":
            text += block.text
    return LlmResponse(
        request_key=request.key,
        tool_input=tool_input,
        text=text,
        stop_reason=str(message.stop_reason),
        usage=_usage(message.usage),
        model=str(message.model),
        latency_s=latency,
    )


class AnthropicClient:
    """Live calls, budget-checked and ledgered; optionally recording real answers as fixtures."""

    def __init__(
        self,
        api_key: str | None,
        *,
        run_id: str,
        ledger: Ledger | None = None,
        budget: Budget | None = None,
        record_dir: Path | None = None,
        purpose: str = "app",
    ) -> None:
        """Create the client. Without a key every call raises ``NoApiKeyError``."""
        self._key = api_key
        self.run_id = run_id
        self.ledger = ledger or Ledger()
        self.budget = budget or Budget(self.ledger)
        self.record_dir = record_dir
        self.purpose = purpose
        self._sdk: Any = None

    def _client(self) -> Any:
        if not self._key:
            raise NoApiKeyError("ANTHROPIC_API_KEY is not set")
        if self._sdk is None:
            import anthropic

            self._sdk = anthropic.Anthropic(api_key=self._key, max_retries=2)
        return self._sdk

    def _record(self, request: LlmRequest, response: LlmResponse, mode: str) -> None:
        import anthropic

        cost = cost_usd(
            response.usage,
            request.model,
            batch=mode == "batch",
            ttl=BATCH_TTL if mode == "batch" else "5m",
        )
        self.ledger.append(
            run_id=self.run_id,
            component=request.component,
            purpose=self.purpose,
            model=response.model,
            mode=mode,
            request=request.key[:12],
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_write_tokens=response.usage.cache_write_tokens,
            cache_read_tokens=response.usage.cache_read_tokens,
            cost_usd=round(cost, 6),
        )
        if self.record_dir is not None:
            fixtures.save(
                self.record_dir,
                request,
                response,
                {
                    "model": response.model,
                    "sdk": f"anthropic {anthropic.__version__}",
                    "mode": mode,
                    "run_id": self.run_id,
                    "purpose": self.purpose,
                },
            )

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Make one call now (the budget is checked first, the answer is ledgered)."""
        client = self._client()
        self.budget.check(worst_case_usd(request), f"{request.component} request")
        started = time.perf_counter()
        try:
            message = client.messages.create(**_params(request))
        except Exception as e:  # SDK errors vary by version; the caller falls back
            raise LlmError(f"{type(e).__name__}: {e}") from e
        response = _response(request, message, time.perf_counter() - started)
        self._record(request, response, "live")
        return response

    def complete_many(self, requests: Sequence[LlmRequest], *, purpose: str) -> list[LlmResponse]:
        """Run many requests through the Batch API (50 % cheaper, usually done within the hour)."""
        client = self._client()
        self.purpose = purpose
        total = sum(worst_case_usd(r, batch=True) for r in requests)
        self.budget.check(total, f"batch of {len(requests)} requests")
        by_id = {f"r{i:04d}": r for i, r in enumerate(requests)}
        batch = client.messages.batches.create(
            requests=[
                {"custom_id": cid, "params": _params(r, BATCH_TTL)} for cid, r in by_id.items()
            ]
        )
        while True:
            batch = client.messages.batches.retrieve(batch.id)
            if batch.processing_status == "ended":
                break
            time.sleep(BATCH_POLL_SECONDS)
        out: dict[str, LlmResponse] = {}
        for result in client.messages.batches.results(batch.id):
            outcome = result.result
            if outcome.type != "succeeded":
                raise LlmError(f"batch request {result.custom_id} {outcome.type}")
            req = by_id[result.custom_id]
            response = _response(req, outcome.message, None)
            self._record(req, response, "batch")
            out[result.custom_id] = response
        return [out[cid] for cid in by_id]
