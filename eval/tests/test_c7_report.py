"""The C7 report and the promotion rule, exercised on SIMULATED recordings in a temp folder.

The recordings written here are made up by the test (a perfect model, a model that blocks days the
person only disliked, ...) to check that the rule's arithmetic is right. They are never committed
and are not model output; the real recordings are in agents/fixtures and are replayed by
`test_c7_result_is_up_to_date`.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from dienstpilot_agents.intake.prompt import build_request
from dienstpilot_agents.llm import fixtures
from dienstpilot_agents.llm.ledger import Ledger
from dienstpilot_agents.llm.types import LlmResponse, Usage

REPO = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_c7_eval", REPO / "eval" / "run_c7_eval.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run = _load()


def _tool_input(
    u: dict[str, Any], *, soft_as_hard: bool = False, follow: bool = False
) -> dict[str, Any]:
    label = u["label"]
    unavailable = list(label["unavailable"])
    soft = [{"date": d, "shift_type": s} for d, s in label["avoid_shift_days"]]
    if soft_as_hard:
        unavailable += [x["date"] for x in soft]
        soft = []
    if follow and u.get("injection") == "date":
        unavailable.append("2026-12-31")
    return {
        "unavailable": sorted(unavailable),
        "avoid_shift_days": soft,
        "prefer_shifts": label["prefer_shifts"],
        "avoid_shifts": label["avoid_shifts"],
        "avoid_weekends": label["avoid_weekends"],
        "clarifying_question": "Welche Tage oder Dienste meinen Sie?" if label["clarify"] else None,
    }


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point the runner at a temp folder; return a function that writes simulated recordings."""
    monkeypatch.setattr(fixtures, "DIR", tmp_path / "fx")
    monkeypatch.setenv("LLM_LEDGER", str(tmp_path / "ledger.jsonl"))
    for name in ("LATENCY", "RESULT", "CHAMPION"):
        monkeypatch.setattr(run, name, tmp_path / f"{name}.json")
    (tmp_path / "LATENCY.json").write_text(json.dumps({"seconds": [1.0] * 30}))

    def record(**kw: Any) -> None:
        month, items = run.load()
        for u in items:
            req = build_request(u["text"], month, u["language"], run.MODEL)
            resp = LlmResponse(
                req.key, _tool_input(u, **kw), "", "tool_use", Usage(500, 80), run.MODEL
            )
            fixtures.save(
                fixtures.DIR, req, resp, {"model": run.MODEL, "sdk": "simulated", "mode": "batch"}
            )

    return record


def test_a_model_that_gets_everything_right_is_promoted(world: Any, tmp_path: Path) -> None:
    world()
    assert run.cmd_report() == 0
    result = json.loads((tmp_path / "RESULT.json").read_text())
    assert result["promoted"] is True and all(result["checks"].values())
    assert result["test"]["llm"]["exact_match"] == 1.0
    assert result["test"]["standin"]["exact_match"] < 0.5
    assert json.loads((tmp_path / "CHAMPION.json").read_text())["promoted"] is True


def test_blocking_days_the_person_only_disliked_fails_the_rule(world: Any, tmp_path: Path) -> None:
    world(soft_as_hard=True)
    run.cmd_report()
    result = json.loads((tmp_path / "RESULT.json").read_text())
    assert result["promoted"] is False
    assert result["test"]["llm"]["soft_to_hard"] > run.MAX_S2H
    assert result["checks"]["2_soft_to_hard_at_most_1_and_fewer_than_standin"] is False
    assert json.loads((tmp_path / "CHAMPION.json").read_text())["promoted"] is False


def test_following_an_injected_instruction_fails_the_rule(world: Any, tmp_path: Path) -> None:
    world(follow=True)
    run.cmd_report()
    result = json.loads((tmp_path / "RESULT.json").read_text())
    assert result["checks"]["4_no_injection_followed"] is False and result["promoted"] is False


def test_a_slow_model_or_a_missing_latency_run_is_not_promoted(world: Any, tmp_path: Path) -> None:
    world()
    (tmp_path / "LATENCY.json").write_text(json.dumps({"seconds": [6.0] * 30}))
    run.cmd_report()
    assert (
        json.loads((tmp_path / "RESULT.json").read_text())["checks"]["6_latency_p95_at_most_5s"]
        is False
    )
    (tmp_path / "LATENCY.json").unlink()
    run.cmd_report()
    assert json.loads((tmp_path / "RESULT.json").read_text())["promoted"] is False


def test_the_report_needs_every_recording(world: Any, tmp_path: Path) -> None:
    world()
    next((fixtures.DIR / "C7").glob("*.json")).unlink()
    assert run.cmd_report() == 2 and not (tmp_path / "RESULT.json").exists()


def test_the_test_run_refuses_an_unfrozen_prompt_and_a_second_run(
    world: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "FROZEN", tmp_path / "frozen.json")
    with pytest.raises(SystemExit, match="not frozen"):
        run.cmd_test()
    run.cmd_freeze()
    Ledger().append(
        run_id=f"c7-{run.PROMPT_VERSION}-test", component="C7", purpose="test", model=run.MODEL,
        mode="batch", request="x", input_tokens=1, output_tokens=1, cache_write_tokens=0,
        cache_read_tokens=0, cost_usd=0.0,
    )  # fmt: skip
    with pytest.raises(SystemExit, match="never re-run"):
        run.cmd_test()


def test_the_committed_result_belongs_to_the_committed_files() -> None:
    """Once the real run exists, CI recomputes c7.json from the recordings and compares."""
    if not (REPO / "eval" / "results" / "c7.json").exists():
        pytest.skip("the pre-registered run has not been made yet")
    real = _load()
    assert real.cmd_report(check=True) == 0
