"""The preference set C7 returns, its tool schema, and the checks every answer passes.

Fields mirror the product's entries (M4): ``unavailable`` is a hard block on a day;
``avoid_shift_days`` is the soft "rather not this shift" of Phase 8b (a day and one shift type);
``prefer_shifts`` and ``avoid_shifts`` are general leanings without a date; ``avoid_weekends``
likewise. There is no field for a reason or for health, on purpose.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

SHIFTS = ("frueh", "spaet", "nacht", "bereitschaft")
TOOL_NAME = "submit_preferences"

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "unavailable": {
            "type": "array",
            "items": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "description": "Dates the person says they cannot work or are not available.",
        },
        "avoid_shift_days": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                    "shift_type": {"type": "string", "enum": list(SHIFTS)},
                },
                "required": ["date", "shift_type"],
                "additionalProperties": False,
            },
            "description": "A date and one shift type the person would rather not work (soft).",
        },
        "prefer_shifts": {
            "type": "array",
            "items": {"type": "string", "enum": list(SHIFTS)},
            "description": "Shift types the person generally prefers (no date).",
        },
        "avoid_shifts": {
            "type": "array",
            "items": {"type": "string", "enum": list(SHIFTS)},
            "description": "Shift types the person generally wants to avoid (no date).",
        },
        "avoid_weekends": {"type": "boolean"},
        "clarifying_question": {
            "type": ["string", "null"],
            "description": "Exactly one short question in the person's language, or null.",
        },
    },
    "required": [
        "unavailable",
        "avoid_shift_days",
        "prefer_shifts",
        "avoid_shifts",
        "avoid_weekends",
        "clarifying_question",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class PreferenceSet:
    """What was understood. Dates are ISO strings inside the roster month."""

    unavailable: list[str] = field(default_factory=list)
    avoid_shift_days: list[tuple[str, str]] = field(default_factory=list)
    prefer_shifts: list[str] = field(default_factory=list)
    avoid_shifts: list[str] = field(default_factory=list)
    avoid_weekends: bool = False
    clarifying_question: str | None = None


class InvalidAnswerError(ValueError):
    """The model's answer does not fit the schema (the caller falls back)."""


# Words that would turn a question into a health inquiry. The model is told not to; this makes
# sure (German and English stems).
HEALTH = re.compile(
    r"krank|diagnos|migr[äa]ne|schmerz|therap|operation|\bop\b|depress|chemo|medikament|"
    r"schwanger|erkrank|arzt\s*termin|sick|ill(ness)?\b|diagnos|migraine|pain|therapy|surgery|"
    r"depress|chemo|medicat|pregnan|disease|doctor'?s appointment|condition",
    re.IGNORECASE,
)
SAFE_QUESTION = {
    "de": "Welche Tage oder Dienste meinen Sie?",
    "en": "Which days or shifts do you mean?",
}


def _iso(value: Any, month: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise InvalidAnswerError(f"not a date: {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as e:
        raise InvalidAnswerError(str(e)) from e
    return value


def parse_answer(
    data: dict[str, Any], month: str, language: str
) -> tuple[PreferenceSet, dict[str, int]]:
    """Validate the tool input and apply the deterministic filters.

    Dates outside the roster month are dropped (counted in the notes); a clarifying question
    that touches health is replaced by a neutral one. Anything malformed raises
    ``InvalidAnswerError``.
    """
    notes = {"dropped_dates": 0, "health_filtered": 0}
    try:
        unavailable = sorted({_iso(d, month) for d in data["unavailable"]})
        soft = sorted(
            {(_iso(x["date"], month), str(x["shift_type"])) for x in data["avoid_shift_days"]}
        )
        prefer = sorted(set(map(str, data["prefer_shifts"])))
        avoid = sorted(set(map(str, data["avoid_shifts"])))
        weekends = data["avoid_weekends"]
        question = data["clarifying_question"]
    except (KeyError, TypeError) as e:
        raise InvalidAnswerError(f"missing or malformed field: {e}") from e
    if not isinstance(weekends, bool):
        raise InvalidAnswerError("avoid_weekends must be a boolean")
    if any(s not in SHIFTS for s in (*prefer, *avoid, *(s for _, s in soft))):
        raise InvalidAnswerError("unknown shift type")
    inside = [d for d in unavailable if d.startswith(month)]
    notes["dropped_dates"] += len(unavailable) - len(inside)
    soft_in = [(d, s) for d, s in soft if d.startswith(month)]
    notes["dropped_dates"] += len(soft) - len(soft_in)
    if question is not None:
        if not isinstance(question, str):
            raise InvalidAnswerError("clarifying_question must be text or null")
        question = question.strip() or None
    if question is not None and HEALTH.search(question):
        question = SAFE_QUESTION.get(language, SAFE_QUESTION["en"])
        notes["health_filtered"] = 1
    return (
        PreferenceSet(inside, soft_in, prefer, avoid, weekends, question),
        notes,
    )
