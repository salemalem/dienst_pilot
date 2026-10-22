"""C7: the request intake agent, served only if its pre-registered rule says so (ADR-020).

``agents/intake/champion.json`` is written by ``eval/run_c7_eval.py``. Without it, or with
``promoted: false``, or without a key (and not in replay mode), the keyword stand-in answers and
the screens say so. The LLM answer never reaches the database: the person confirms what was
understood first. Any model error falls back to the stand-in for that request, labelled.
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import cast

from dienstpilot.engines.standins import STANDIN_VERSION, IntakeStandIn
from dienstpilot.shared.ports import EngineInfo, IntakeParser, ParsedPreferences, ShiftOnDay
from dienstpilot.shared.settings import Settings
from dienstpilot_agents.intake.prompt import PROMPT_VERSION, build_request
from dienstpilot_agents.intake.schema import InvalidAnswerError, parse_answer
from dienstpilot_agents.llm.anthropic_client import AnthropicClient
from dienstpilot_agents.llm.fixtures import ReplayClient
from dienstpilot_agents.llm.types import LlmClient, LlmError

log = logging.getLogger(__name__)
CHAMPION = Path(__file__).resolve().parents[4] / "agents" / "intake" / "champion.json"
RESULT = Path(__file__).resolve().parents[4] / "eval" / "results" / "c7.json"


def champion() -> dict[str, object] | None:
    """Return the evaluation's verdict (``champion.json``), if the evaluation has been run."""
    if not CHAMPION.exists():
        return None
    return cast("dict[str, object]", json.loads(CHAMPION.read_text(encoding="utf-8")))


def standin_note() -> str:
    """Say, in the stand-in's note, whether an LLM version was evaluated."""
    verdict = champion()
    if verdict is None:
        return "Keyword and date matching (DE/EN). The LLM version has not been evaluated yet."
    if verdict["promoted"]:
        return "Keyword and date matching (DE/EN). Used because no model access is configured."
    return (
        "Keyword and date matching (DE/EN). The LLM version was evaluated and did not meet the "
        "pre-registered promotion rule, so this stays (model card c7-request-intake)."
    )


class LlmIntake(IntakeParser):
    """C7 with a language model: schema-validated tool output, filters, fallback to the stand-in."""

    def __init__(self, client: LlmClient, model: str, replay: bool, fallback: IntakeParser) -> None:
        """Use ``client`` for ``model``; ``fallback`` answers when the model cannot."""
        self._client, self._model, self._replay, self._fallback = client, model, replay, fallback
        how = "recorded responses" if replay else "live"
        self.info = EngineInfo(
            "C7",
            "built",
            f"{PROMPT_VERSION}+{model}",
            f"Language model ({model}, {how}) with schema-checked output and deterministic "
            "filters; promoted by the pre-registered rule; the person confirms the result.",
            None,
        )

    def parse(self, text: str, month: date, language: str) -> ParsedPreferences:
        """Parse untrusted free text; on any model problem answer with the stand-in, labelled."""
        try:
            response = self._client.complete(
                build_request(text, month.strftime("%Y-%m"), language, self._model)
            )
            if response.tool_input is None:
                raise InvalidAnswerError("no tool call in the answer")
            answer, _ = parse_answer(response.tool_input, month.strftime("%Y-%m"), language)
        except (LlmError, InvalidAnswerError) as e:
            log.warning("C7 fell back to the stand-in: %s", e)
            p = self._fallback.parse(text, month, language)
            return ParsedPreferences(
                p.unavailable,
                p.prefer_shifts,
                p.avoid_shifts,
                p.avoid_weekends,
                p.clarifying_question,
                p.avoid_shift_days,
                engine_info=EngineInfo(
                    "C7",
                    "stand-in",
                    STANDIN_VERSION,
                    "Keyword and date matching: the language model could not answer this request.",
                    None,
                ),
            )
        return ParsedPreferences(
            [date.fromisoformat(d) for d in answer.unavailable],
            answer.prefer_shifts,
            answer.avoid_shifts,
            answer.avoid_weekends,
            answer.clarifying_question,
            [ShiftOnDay(date.fromisoformat(d), s) for d, s in answer.avoid_shift_days],
            ai_generated=True,
            replayed=response.replayed,
        )


def build_intake(settings: Settings) -> IntakeParser:
    """Return the engine for C7 under the current settings."""
    standin = IntakeStandIn(standin_note())
    verdict = champion()
    if verdict is None or not verdict["promoted"] or settings.llm_mode == "off":
        return standin
    mode = settings.llm_mode
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    client: LlmClient
    if mode == "replay":
        client = ReplayClient()
    elif key and mode in ("auto", "live"):
        client = AnthropicClient(key, run_id="app", purpose="app")
    else:
        return standin
    return LlmIntake(client, settings.llm_model_intake, mode == "replay", standin)
