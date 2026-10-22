"""Cost, ledger, budget guard, live-call parameters and recordings. No network: a fake SDK."""

import json
from pathlib import Path
from types import SimpleNamespace as Fake
from typing import Any

import pytest

from dienstpilot_agents.intake.prompt import build_request
from dienstpilot_agents.llm import fixtures
from dienstpilot_agents.llm import ledger as ledger_mod
from dienstpilot_agents.llm.anthropic_client import AnthropicClient, _params
from dienstpilot_agents.llm.budget import LIMIT_USD, Budget, worst_case_usd
from dienstpilot_agents.llm.ledger import Ledger
from dienstpilot_agents.llm.pricing import PATH, cost_usd, price
from dienstpilot_agents.llm.types import (
    BudgetExceededError,
    LlmError,
    MissingFixtureError,
    NoApiKeyError,
    Usage,
)

MODEL = "claude-haiku-5-5"
REQ = build_request("Am 7.12. kann ich nicht.", "2026-12", "de", MODEL)


# --- prices -----------------------------------------------------------------------------------


def test_pricing_file_matches_the_pricing_page_figures_it_was_copied_from() -> None:
    doc = json.loads(PATH.read_text())
    assert doc["source"].startswith("https://platform.claude.com/") and doc["retrieved"]
    p = price(MODEL)
    assert (p.input, p.output, p.cache_write_5m, p.cache_write_1h, p.cache_read) == (
        0.10, 0.50, 0.125, 0.20, 0.01,
    )  # fmt: skip
    assert (p.batch_input, p.batch_output, p.long_context_threshold) == (0.05, 0.25, 100_000)


def test_cost_arithmetic() -> None:
    u = Usage(input_tokens=1000, output_tokens=100, cache_write_tokens=2000, cache_read_tokens=4000)
    live = (1000 * 0.10 + 100 * 0.50 + 2000 * 0.125 + 4000 * 0.01) / 1e6
    assert cost_usd(u, MODEL) == pytest.approx(live)
    batch = (1000 * 0.05 + 100 * 0.25 + 2000 * 0.20 * 0.5 + 4000 * 0.01 * 0.5) / 1e6
    assert cost_usd(u, MODEL, batch=True, ttl="1h") == pytest.approx(batch)
    assert cost_usd(u, MODEL, batch=True, ttl="1h") < cost_usd(u, MODEL)


def test_a_prompt_over_the_long_context_threshold_is_refused() -> None:
    with pytest.raises(LlmError, match="threshold"):
        cost_usd(Usage(input_tokens=100_001), MODEL)
    cost_usd(Usage(input_tokens=100_000), MODEL)


# --- ledger and budget ------------------------------------------------------------------------


def _entry(**kw: Any) -> dict[str, Any]:
    base = {
        "run_id": "t",
        "component": "C7",
        "purpose": "test",
        "model": MODEL,
        "mode": "live",
        "request": "abc",
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "cost_usd": 0.5,
    }
    return {**base, **kw}


def test_the_ledger_is_append_only_and_cumulative(tmp_path: Path) -> None:
    lg = Ledger(tmp_path / "l.jsonl")
    assert lg.total_usd() == 0.0
    a = lg.append(**_entry(cost_usd=0.25))
    b = lg.append(**_entry(cost_usd=0.5))
    assert (a.seq, b.seq, b.cumulative_usd) == (1, 2, 0.75) and lg.total_usd() == 0.75
    assert Ledger(tmp_path / "l.jsonl").total_usd() == 0.75  # survives a new process


def test_the_guard_refuses_a_call_that_could_pass_the_limit(tmp_path: Path) -> None:
    lg = Ledger(tmp_path / "l.jsonl")
    lg.append(**_entry(cost_usd=LIMIT_USD - 0.0001))
    b = Budget(lg)
    with pytest.raises(BudgetExceededError):
        b.check(worst_case_usd(REQ), "one request")
    b.check(0.00005, "tiny")  # still fits
    assert Budget(Ledger(tmp_path / "none.jsonl")).remaining() == LIMIT_USD


def test_the_limit_is_4_50_dollars_and_a_prompt_is_far_below_the_price_tier() -> None:
    assert LIMIT_USD == 4.50
    assert worst_case_usd(REQ) < 0.001  # one C7 request, worst case, under a tenth of a cent


# --- the live client with a fake SDK ------------------------------------------------------------


class FakeSdk:
    """Stands in for anthropic.Anthropic; records what it was asked."""

    def __init__(self, tool_input: dict[str, Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.batch_requests: list[dict[str, Any]] = []
        self.tool_input = tool_input
        self.messages = Fake(
            create=self._create,
            batches=Fake(create=self._bcreate, retrieve=self._bget, results=self._bres),
        )

    def _message(self) -> Any:
        return Fake(
            content=[Fake(type="tool_use", input=self.tool_input)],
            stop_reason="tool_use",
            model=MODEL,
            usage=Fake(
                input_tokens=300,
                output_tokens=60,
                cache_creation_input_tokens=1500,
                cache_read_input_tokens=0,
            ),
        )

    def _create(self, **params: Any) -> Any:
        self.calls.append(params)
        return self._message()

    def _bcreate(self, requests: list[dict[str, Any]]) -> Any:
        self.batch_requests = requests
        return Fake(id="msgbatch_1")

    def _bget(self, _id: str) -> Any:
        return Fake(id="msgbatch_1", processing_status="ended")

    def _bres(self, _id: str) -> Any:
        return [
            Fake(custom_id=r["custom_id"], result=Fake(type="succeeded", message=self._message()))
            for r in self.batch_requests
        ]


def _client(
    tmp_path: Path, tool_input: dict[str, Any] | None = None, **kw: Any
) -> tuple[AnthropicClient, FakeSdk]:
    c = AnthropicClient("sk-test", run_id="t", ledger=Ledger(tmp_path / "l.jsonl"), **kw)
    sdk = FakeSdk(tool_input or {"unavailable": []})
    c._sdk = sdk
    return c, sdk


def test_a_live_call_sends_no_thinking_caches_the_prompt_and_is_ledgered(tmp_path: Path) -> None:
    c, sdk = _client(tmp_path)
    r = c.complete(REQ)
    sent = sdk.calls[0]
    assert not {"thinking", "temperature", "top_p", "top_k"} & set(sent)
    assert sent["model"] == MODEL and sent["max_tokens"] == REQ.max_tokens
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["tool_choice"] == {"type": "tool", "name": "submit_preferences"}
    assert r.tool_input == {"unavailable": []} and r.usage.cache_write_tokens == 1500
    [e] = c.ledger.entries()
    assert e.cost_usd == pytest.approx(cost_usd(r.usage, MODEL), abs=1e-6) and e.mode == "live"
    assert "kann ich nicht" not in json.dumps(e.__dict__)  # no prompt text in the ledger


def test_the_budget_stops_the_call_before_it_is_sent(tmp_path: Path) -> None:
    c, sdk = _client(tmp_path)
    c.ledger.append(**_entry(cost_usd=LIMIT_USD))
    with pytest.raises(BudgetExceededError):
        c.complete(REQ)
    assert sdk.calls == []


def test_no_key_means_no_call() -> None:
    with pytest.raises(NoApiKeyError):
        AnthropicClient(None, run_id="t").complete(REQ)


def test_a_batch_costs_half_uses_the_one_hour_cache_and_is_ledgered(tmp_path: Path) -> None:
    c, sdk = _client(tmp_path)
    reqs = [build_request(f"Am {d}.12. kann ich nicht.", "2026-12", "de", MODEL) for d in (3, 4, 5)]
    out = c.complete_many(reqs, purpose="test")
    assert [r.tool_input for r in out] == [{"unavailable": []}] * 3
    assert {b["custom_id"] for b in sdk.batch_requests} == {"r0000", "r0001", "r0002"}
    assert sdk.batch_requests[0]["params"]["system"][0]["cache_control"] == {
        "type": "ephemeral",
        "ttl": "1h",
    }
    entries = c.ledger.entries()
    assert [e.mode for e in entries] == ["batch"] * 3 and all(e.purpose == "test" for e in entries)
    u = out[0].usage
    assert entries[0].cost_usd == pytest.approx(cost_usd(u, MODEL, batch=True, ttl="1h"), abs=1e-6)
    assert entries[0].cost_usd < cost_usd(u, MODEL)


def test_a_batch_that_could_pass_the_limit_is_not_started(tmp_path: Path) -> None:
    c, sdk = _client(tmp_path)
    c.ledger.append(**_entry(cost_usd=LIMIT_USD - 0.00001))
    with pytest.raises(BudgetExceededError):
        c.complete_many([REQ], purpose="test")
    assert sdk.batch_requests == []


# --- recordings -------------------------------------------------------------------------------


def test_a_recorded_call_replays_without_the_network(tmp_path: Path) -> None:
    rec = tmp_path / "fx"
    c, _ = _client(tmp_path, {"unavailable": ["2026-12-07"]}, record_dir=rec)
    live = c.complete(REQ)
    saved = json.loads(fixtures.path_for(rec, REQ).read_text())
    assert saved["recorded"]["model"] == MODEL and saved["recorded"]["sdk"].startswith("anthropic ")
    replayed = fixtures.ReplayClient(rec).complete(REQ)
    assert (
        replayed.replayed
        and replayed.tool_input == live.tool_input
        and replayed.usage == live.usage
    )


def test_replay_never_guesses(tmp_path: Path) -> None:
    other = build_request("etwas ganz anderes", "2026-12", "de", MODEL)
    with pytest.raises(MissingFixtureError):
        fixtures.ReplayClient(tmp_path).complete(other)


def test_params_are_a_pure_function_of_the_request() -> None:
    assert _params(REQ) == _params(REQ)
    assert _params(REQ, "1h")["system"][0]["cache_control"]["ttl"] == "1h"


# --- committed files --------------------------------------------------------------------------


def test_every_committed_fixture_is_a_real_recording_of_its_own_request() -> None:
    import hashlib

    for p in fixtures.DIR.glob("*/*.json"):
        doc = json.loads(p.read_text())
        raw = json.dumps(doc["request"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        assert hashlib.sha256(raw.encode()).hexdigest() == doc["request_key"] == p.stem
        assert doc["recorded"]["model"].startswith("claude-") and doc["recorded"]["sdk"]
        assert doc["recorded"]["mode"] in ("live", "batch")
        assert "thinking" not in doc["request"]


def test_the_committed_ledger_is_consistent_and_within_the_budget() -> None:
    lg = Ledger(ledger_mod.PATH)
    entries = lg.entries()
    running = 0.0
    for i, e in enumerate(entries, start=1):
        usage = Usage(e.input_tokens, e.output_tokens, e.cache_write_tokens, e.cache_read_tokens)
        expected = cost_usd(
            usage, e.model, batch=e.mode == "batch", ttl="1h" if e.mode == "batch" else "5m"
        )
        assert e.seq == i and e.cost_usd == pytest.approx(expected, abs=2e-6), e
        running = round(running + e.cost_usd, 6)
        assert e.cumulative_usd == pytest.approx(running, abs=1e-5)
    assert lg.total_usd() <= LIMIT_USD
