"""C8: the planner copilot. The agent answers only what its pre-registered gates let it (ADR-021).

``agents/copilot/champion.json`` is written by ``eval/run_c8_eval.py``. A capability that is
``false`` there (lookups, rules) is answered by the keyword stand-in, whatever the model could do.
Which capability a question belongs to is decided by keywords, not by a model, so the agent only
sees the kinds of question it was evaluated and released for. Without a key (and not in replay
mode) the stand-in answers everything and the screens say so.
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, cast

from dienstpilot.engines.standins import CopilotStandIn
from dienstpilot.shared.ports import Copilot, CopilotAnswer, CopilotFacts, EngineInfo
from dienstpilot.shared.settings import Settings
from dienstpilot_agents.copilot import agent as agent_graph
from dienstpilot_agents.copilot.connect import mcp_connect
from dienstpilot_agents.copilot.guard import Aliases
from dienstpilot_agents.copilot.outcome import Outcome, load_demo, outcome, record
from dienstpilot_agents.copilot.prompt import PROMPT_VERSION
from dienstpilot_agents.copilot.tools import McpToolbox
from dienstpilot_agents.llm.anthropic_client import AnthropicClient
from dienstpilot_agents.llm.types import LlmClient

log = logging.getLogger(__name__)
CHAMPION = Path(__file__).resolve().parents[4] / "agents" / "copilot" / "champion.json"
Capability = Literal["whatifs", "drafting"]
WHATIF = re.compile(
    "|".join(
        [
            r"was passiert,? wenn",
            r"was wäre,? wenn",
            r"what if",
            r"what happens if",
            r"regelkonform",
            r"comply with the rules",
            r"gibt .{0,60} ab\b",
            r"hands? .{0,60} to\b",
            r"hand over",
        ]
    ),
    re.IGNORECASE,
)
DRAFT = re.compile(
    "|".join(
        [
            r"formuliere",
            r"entwirf",
            r"entwerfe",
            r"schreibe (?:eine |einen )?(?:kurze |kurzen )?(?:begründung|ankündigung)",
            r"\bdraft\b",
            r"write (?:a |an )?(?:one-sentence |short )?(?:reason|announcement)",
            r"ankündigung",
            r"announcement",
        ]
    ),
    re.IGNORECASE,
)
Runner = Callable[..., Awaitable[Outcome]]


def champion() -> dict[str, Any] | None:
    """Return the evaluation's verdict (``champion.json``), if the evaluation has been run."""
    if not CHAMPION.exists():
        return None
    return cast("dict[str, Any]", json.loads(CHAMPION.read_text(encoding="utf-8")))


def capability(question: str) -> Capability | None:
    """Return which released capability a question belongs to (keywords), or None."""
    if DRAFT.search(question):  # first: a drafting request may describe a hand-over too
        return "drafting"
    if WHATIF.search(question):
        return "whatifs"
    return None


class NoRecordingError(LookupError):
    """Replay mode has no recording for this question."""


class C8Copilot(Copilot):
    """The stand-in for lookups and rules, the agent for the capabilities that passed the gates."""

    def __init__(
        self,
        standin: CopilotStandIn,
        verdict: dict[str, Any] | None,
        settings: Settings,
        client: LlmClient | None,
        replay: bool,
        runner: Runner | None = None,
    ) -> None:
        """Without ``client`` the agent is unavailable; ``runner`` stands in for it in tests."""
        self._standin, self._verdict, self._settings = standin, verdict, settings
        self._client, self._replay, self._runner = client, replay, runner
        self.served = {k for k, v in (verdict or {}).get("served", {}).items() if v}
        self.available = (
            verdict is not None
            and bool(verdict.get("safety_pass"))
            and (client is not None or replay or runner is not None)
        )
        self.info = self._describe()

    def _describe(self) -> EngineInfo:
        if not self.available or not self.served:
            note = self._standin.info.note
            if self._verdict is not None and not self.served:
                note += " The agent was evaluated and did not pass its gates (model card c8)."
            elif self._verdict is not None:
                note += " The agent needs model access, which is not configured."
            return EngineInfo("C8", "stand-in", self._standin.info.version, note, 10)
        how = "recorded responses" if self._replay else "live"
        caps = ", ".join(sorted(self.served))
        return EngineInfo(
            "C8",
            "partial",
            f"{PROMPT_VERSION}+{self._settings.llm_model_copilot}",
            f"LangGraph agent ({self._settings.llm_model_copilot}, {how}) for {caps}; keyword "
            "stand-in for the rest. It reads and proposes only; nothing it writes is applied.",
            None,
        )

    def ask(self, question: str, language: str, facts: CopilotFacts) -> CopilotAnswer:
        """Answer with the stand-in (lookups and rules; also anything the agent may not answer)."""
        return self._standin.ask(question, language, facts)

    def serves(self, question: str, role: str, language: str) -> Capability | None:
        """Return the capability the agent will answer this question with, or None."""
        cap = capability(question)
        if cap is None or not self.available or cap not in self.served:
            return None
        if cap == "drafting" and role != "planner":
            return None  # only the Planner has the tools that save a draft
        if self._replay and self._runner is None and load_demo(role, language, question) is None:
            return None
        return cap

    async def answer(
        self,
        *,
        question: str,
        language: str,
        role: str,
        today: str,
        staff: dict[str, str],
        token: str,
    ) -> Outcome:
        """Run the agent (or return the recording) for one question."""
        if self._runner is not None:
            return await self._runner(
                question=question,
                language=language,
                role=role,
                today=today,
                staff=staff,
                token=token,
            )
        aliases = Aliases(staff)
        if self._replay:
            rec = load_demo(role, language, question)
            if rec is None:
                raise NoRecordingError(question)
            return outcome(rec, aliases, language)
        assert self._client is not None
        res = await agent_graph.run(
            question=question,
            language=language,
            role=role,
            today=today,
            model=self._settings.llm_model_copilot,
            client=self._client,
            toolbox=McpToolbox(mcp_connect(self._settings.mcp_url, token)),
            aliases=aliases,
        )
        return outcome(record(res, role=role, language=language), aliases, language)

    @property
    def standin_info(self) -> EngineInfo:
        """Describe the stand-in (it answers whatever the agent does not)."""
        return self._standin.info

    @property
    def replayed(self) -> bool:
        """Whether answers come from recordings."""
        return self._replay


def build_copilot(settings: Settings) -> C8Copilot:
    """Return the C8 engine under the current settings."""
    standin = CopilotStandIn()
    verdict = champion()
    mode = settings.llm_mode
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    client: LlmClient | None = None
    replay = False
    if verdict is not None and mode != "off":
        if mode == "replay":
            replay = True
        elif key and mode in ("auto", "live"):
            client = AnthropicClient(key, run_id="app-c8", purpose="app")
    return C8Copilot(standin, verdict, settings, client, replay)
