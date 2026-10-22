"""Recorded responses: real answers of the real model, keyed by the request, committed.

Replay mode reads them and never calls the network, so development, debugging and CI cost nothing.
A fixture is only ever written by a live call (``AnthropicClient`` with a ``record_dir``); nobody
writes one by hand, and a test checks that each one carries the model and SDK that produced it.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from dienstpilot_agents.llm.types import (
    FORMAT,
    LlmRequest,
    LlmResponse,
    MissingFixtureError,
    Usage,
)

DIR = Path(__file__).resolve().parents[4] / "agents" / "fixtures"


def path_for(directory: Path, request: LlmRequest) -> Path:
    """Return where the recording of this request lives."""
    return directory / request.component / f"{request.key}.json"


def save(directory: Path, request: LlmRequest, response: LlmResponse, meta: dict[str, str]) -> Path:
    """Write the recording of a live call."""
    target = path_for(directory, request)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "format": FORMAT,
        "request_key": request.key,
        "request": request.canonical(),
        "response": {
            "tool_input": response.tool_input,
            "text": response.text,
            "stop_reason": response.stop_reason,
            "model": response.model,
            "usage": response.usage.__dict__,
        },
        "recorded": meta,
    }
    target.write_text(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return target


class ReplayClient:
    """Answers from recordings. A request without a recording is an error, never a guess."""

    def __init__(self, directory: Path | None = None) -> None:
        """Read recordings from ``directory`` (default ``agents/fixtures``)."""
        self.directory = directory or DIR

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Return the recorded answer to ``request``."""
        p = path_for(self.directory, request)
        if not p.exists():
            raise MissingFixtureError(
                f"no recording for {request.component} request {request.key[:12]} "
                "(replay mode makes no calls; re-record with `make record-llm`)"
            )
        doc = json.loads(p.read_text(encoding="utf-8"))
        r = doc["response"]
        return LlmResponse(
            request_key=request.key,
            tool_input=r["tool_input"],
            text=r["text"],
            stop_reason=r["stop_reason"],
            usage=Usage(**r["usage"]),
            model=r["model"],
            replayed=True,
            meta=doc["recorded"],
        )

    def complete_many(self, requests: Sequence[LlmRequest], *, purpose: str) -> list[LlmResponse]:
        """Return the recorded answers, in order."""
        return [self.complete(r) for r in requests]
