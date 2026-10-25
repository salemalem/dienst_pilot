"""What a C8 run looks like to the application: a record (JSON) and a displayable outcome.

``record`` turns a ``RunResult`` into the JSON the evaluation stores and the demo recordings are
made of; ``outcome`` turns such a record into what the screens show (names restored, sources
listed in words). Live runs and replayed recordings go through the same two functions.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dienstpilot_agents.copilot.agent import RunResult
from dienstpilot_agents.copilot.guard import Aliases
from dienstpilot_agents.copilot.scoring import regrade, results_of
from dienstpilot_agents.copilot.tools import LOCAL, WRITE_TOOLS

DEMO_DIR = Path(__file__).resolve().parents[4] / "agents" / "fixtures" / "C8" / "demo"

SOURCE_LABELS = {
    "get_roster": ("Dienstplan des Monats", "Roster of the month"),
    "get_assignments_for": ("Dienste einer Person", "One physician's shifts"),
    "get_burden_ledger": ("Belastungskonto (Nächte, Wochenenden, Feiertage)", "Burden ledger"),
    "get_coverage": ("Besetzung je Dienst", "Coverage per shift"),
    "run_what_if": (
        "Was-wäre-wenn-Prüfung durch den Validator (C2)",
        "What-if check by the validator (C2)",
    ),
    "validate": ("Regelprüfung durch den Validator (C2)", "Rule check by the validator (C2)"),
    "get_variants": ("Planvarianten", "Plan variants"),
    "get_history": (
        "Änderungen, Entscheidungen und Vorschläge",
        "Changes, decisions and proposals",
    ),
    "search_rules": ("Regelwerk-Suche", "Rulebook search"),
    "get_rule": ("Regelwerk-Passage", "Rulebook passage"),
    "get_absence_forecast": ("Abwesenheitsprognose", "Absence forecast"),
    "get_cover_candidates": ("Vertretungskandidaten", "Cover candidates"),
    "create_proposal": ("Vorschlag im Posteingang angelegt", "Proposal put in the inbox"),
    "draft_announcement": (
        "Ankündigungsentwurf im Posteingang gespeichert",
        "Announcement draft saved in the inbox",
    ),
}


def demo_key(role: str, language: str, question: str) -> str:
    """Return the file stem of the recording of a demo question."""
    raw = json.dumps([role, language, " ".join(question.split()).lower()], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def record(res: RunResult, *, role: str, language: str) -> dict[str, Any]:
    """Return the JSON-able record of a run (what the evaluation and the recordings store)."""
    usage = {
        k: sum(t.usage[k] for t in res.turns)
        for k in ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens")
    }
    return {
        "role": role,
        "language": language,
        "question": res.question,
        "final": res.final,
        "value_id": res.value_id,
        "served": res.served,
        "fallback": res.fallback,
        "fallback_reason": res.fallback_reason,
        "ungrounded": res.ungrounded,
        "aborted": res.aborted,
        "findings": [f.__dict__ for f in res.findings],
        "calls": [c.__dict__ for c in res.calls],
        "turns": [
            {
                "request_key": x.request_key,
                "blocks": x.blocks,
                "tool_results": x.tool_results,
                "usage": x.usage,
                "latency_s": x.latency_s,
                "model": x.model,
                "new_text": x.new_text,
            }
            for x in res.turns
        ],
        "usage": usage,
    }


@dataclass
class Outcome:
    """What the screens show for an agent answer."""

    answer: str
    fallback: bool
    fallback_reason: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)
    what_if: dict[str, Any] | None = None
    citations: list[str] = field(default_factory=list)
    wrote: list[str] = field(default_factory=list)
    privacy_stopped: bool = False


def outcome(rec: dict[str, Any], aliases: Aliases, language: str) -> Outcome:
    """Build the displayable outcome from a record (names restored, sources in words)."""
    rec = regrade({**rec, "meta": rec.get("meta", {})})
    de = language == "de"
    sources = []
    for c in rec["calls"]:
        if c["name"] == LOCAL or c["is_error"]:
            continue
        label = SOURCE_LABELS.get(c["name"], (c["name"], c["name"]))[0 if de else 1]
        args = {
            k: aliases.from_model(str(v))
            for k, v in c["args"].items()
            if not isinstance(v, (list, dict))
        }
        sources.append({"tool": c["name"], "label": label, "args": args})
    what_if = None
    final = rec["final"] or {}
    checks = results_of(rec, "run_what_if")
    if checks and not rec["fallback"]:
        last = checks[-1] or {}
        what_if = {
            "valid": bool(last.get("valid")),
            "violations": [
                {
                    "rule": v["rule"],
                    "date": v["date"],
                    "person": aliases.from_model(v["staff_id"]) if v.get("staff_id") else None,
                }
                for v in last.get("introduced", [])
            ],
            "uncovered": last.get("uncovered", []),
            "validator_version": last.get("validator_version"),
        }
    return Outcome(
        answer=rec["served"]
        if rec["fallback"]
        else aliases.from_model(str(final.get("answer", ""))),
        fallback=bool(rec["fallback"]),
        fallback_reason=rec.get("fallback_reason"),
        sources=sources,
        what_if=what_if,
        citations=list(final.get("citations") or []),
        wrote=[c["name"] for c in rec["calls"] if c["name"] in WRITE_TOOLS],
        privacy_stopped=rec["aborted"] == "privacy",
    )


def load_demo(
    role: str, language: str, question: str, directory: Path | None = None
) -> dict[str, Any] | None:
    """Return the recording of a demo question, if there is one."""
    p = (directory or DEMO_DIR) / f"{demo_key(role, language, question)}.json"
    return None if not p.exists() else dict(json.loads(p.read_text(encoding="utf-8")))
