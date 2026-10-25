"""Requests and responses of the LLM port. Plain data; nothing here knows a vendor."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

FORMAT = 1


class LlmError(Exception):
    """A call failed (network, API error, refusal to answer in the schema)."""


class MissingFixtureError(LlmError):
    """Replay mode has no recording for this request (it never calls the network)."""


class BudgetExceededError(LlmError):
    """The call would take the phase's paid spending over its limit."""


class NoApiKeyError(LlmError):
    """A live call was asked for without ANTHROPIC_API_KEY."""


@dataclass(frozen=True)
class SystemBlock:
    """A block of the system prompt. ``cache`` marks the end of what may be cached."""

    text: str
    cache: bool = False


@dataclass(frozen=True)
class Tool:
    """A tool the model may (here: must) call, with a JSON Schema for its input."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class LlmRequest:
    """One model call. No extended thinking and no sampling parameters exist in this port."""

    component: str  # "C7" or "C8"
    model: str
    system: tuple[SystemBlock, ...]
    messages: tuple[dict[str, Any], ...]
    max_tokens: int
    prompt_version: str
    tools: tuple[Tool, ...] = ()
    force_tool: str | None = None
    cache_last_message: bool = False  # multi-turn tool loops: cache the conversation so far

    def canonical(self) -> dict[str, Any]:
        """Return everything that shapes the answer, as plain JSON data."""
        d = asdict(self)
        d["format"] = FORMAT
        if not d["cache_last_message"]:
            del d[
                "cache_last_message"
            ]  # keeps the keys of recordings made before the field existed
        return d

    @property
    def key(self) -> str:
        """The fixture key: SHA-256 of the canonical request."""
        raw = json.dumps(
            self.canonical(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Usage:
    """Tokens of one call, as the API reports them."""

    input_tokens: int = 0  # not read from and not written to the cache
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        """The prompt length the price tier is chosen by (cache reads and writes count)."""
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens


@dataclass(frozen=True)
class LlmResponse:
    """The model's answer."""

    request_key: str
    tool_input: dict[str, Any] | None
    text: str
    stop_reason: str
    usage: Usage
    model: str
    replayed: bool = False
    latency_s: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    blocks: list[dict[str, Any]] = field(default_factory=list)  # the assistant's content blocks


class LlmClient(Protocol):
    """What a component needs from a model provider."""

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Answer one request now."""

    def complete_many(self, requests: Sequence[LlmRequest], *, purpose: str) -> list[LlmResponse]:
        """Answer many requests that nobody waits for (batch pricing where available)."""
