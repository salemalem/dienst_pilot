"""Deterministic stand-ins for C4–C8.

They have the shape of the real components but none of their method: no trained model, no LLM.
Every response that uses one says so.
"""

import re
from collections import Counter
from datetime import date, timedelta
from typing import Literal

from dienstpilot.shared.ports import (
    Copilot,
    CopilotAnswer,
    CopilotFacts,
    CoverCandidate,
    CoverRanker,
    EngineInfo,
    IntakeParser,
    LeaveFeasibility,
    LeaveHint,
    ParsedPreferences,
    PreferenceLearner,
    PreferenceSuggestion,
)

STANDIN_VERSION = "standin-0.1"


class PreferenceStandIn(PreferenceLearner):
    """C4 stand-in: counts how often a weekday and shift was wished for or swapped away."""

    info = EngineInfo(
        "C4",
        "stand-in",
        STANDIN_VERSION,
        "Counts of stated wishes and swapped-away shifts; Bayesian model in phase 8.",
        8,
    )

    def suggest(
        self, wishes: list[tuple[date, str | None]], swapped_away: list[tuple[date, str]]
    ) -> list[PreferenceSuggestion]:
        """Suggest at most three preferences with enough evidence."""
        prefer = Counter((d.weekday(), s) for d, s in wishes if s)
        avoid = Counter((d.weekday(), s) for d, s in swapped_away)
        out = [
            PreferenceSuggestion("avoid", wd, s, n) for (wd, s), n in avoid.most_common() if n >= 2
        ]
        out += [
            PreferenceSuggestion("prefer", wd, s, n)
            for (wd, s), n in prefer.most_common()
            if n >= 3
        ]
        return sorted(out, key=lambda x: (-x.evidence, x.kind, x.weekday, x.shift_type))[:3]


class CoverRankStandIn(CoverRanker):
    """C5 stand-in: least cover burden first, then lowest hours against contract. No P(accept)."""

    info = EngineInfo(
        "C5",
        "stand-in",
        STANDIN_VERSION,
        "Orders by covers in the last 90 days, then hours vs contract; classifier in phase 8.",
        8,
    )

    def rank(self, candidates: list[CoverCandidate]) -> list[CoverCandidate]:
        """Return candidates in asking order."""
        return sorted(candidates, key=lambda c: (c.covers_last_90_days, c.hours_ratio, c.staff_id))


class LeaveFeasibilityStandIn(LeaveFeasibility):
    """C6 stand-in: compares approved leave on the requested days with the concurrency limit."""

    info = EngineInfo(
        "C6",
        "stand-in",
        STANDIN_VERSION,
        "Approved leave per day against the concurrency limit; surrogate model in phase 8.",
        8,
    )

    def hint(
        self, start: date, end: date, approved_leave_per_day: dict[date, int], limit: int
    ) -> LeaveHint:
        """Return a hint for the requested days."""
        d, worst, any_overlap = start, 0, 0
        while d <= end:
            n = approved_leave_per_day.get(d, 0)
            worst = max(worst, n)
            any_overlap = max(any_overlap, n)
            d += timedelta(days=1)
        outcome: Literal["coverable", "tight", "not_coverable"] = (
            "not_coverable" if worst >= limit else "tight" if worst >= limit - 1 else "coverable"
        )
        return LeaveHint(outcome, worst, limit, any_overlap)


SHIFT_WORDS = {
    "frueh": ("früh", "fruh", "frühdienst", "early"),
    "spaet": ("spät", "spat", "spätdienst", "late"),
    "nacht": ("nacht", "nächte", "nachtdienst", "night", "nights"),
    "bereitschaft": ("bereitschaft", "on-call", "on call"),
}
DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.?(?:(\d{4}))?")


class IntakeStandIn(IntakeParser):
    """C7 stand-in: keywords and dates in German or English. No LLM.

    The text is only searched for known words and dates; nothing in it is executed or followed.
    """

    info = EngineInfo(
        "C7",
        "stand-in",
        STANDIN_VERSION,
        "Keyword and date matching (DE/EN); LLM with structured output in phase 10.",
        10,
    )

    def parse(self, text: str, month: date, language: str) -> ParsedPreferences:
        """Parse untrusted free text into a typed preference set."""
        t = text.lower()
        unavailable = []
        for dd, mm, yyyy in DATE_RE.findall(t):
            year = int(yyyy) if yyyy else month.year
            try:
                unavailable.append(date(year, int(mm), int(dd)))
            except ValueError:
                continue
        prefer, avoid = [], []
        m = re.search(r"(lieber|rather|prefer)\s+(\w+)\s+(als|than)\s+(\w+)", t)
        if m:
            for code, words in SHIFT_WORDS.items():
                if m.group(2) in words:
                    prefer.append(code)
        avoid_weekends = bool(
            re.search(r"(als|than|keine|no|not)\s+(\w+\s+)?(wochenende|weekend)", t)
        )
        for code, words in SHIFT_WORDS.items():
            if re.search(r"(keine|kein|no|not)\s+(" + "|".join(map(re.escape, words)) + r")", t):
                avoid.append(code)
        understood = bool(unavailable or prefer or avoid or avoid_weekends)
        question = None
        if not understood:
            question = (
                "Welche Tage oder Dienste meinen Sie?"
                if language == "de"
                else "Which days or shifts do you mean?"
            )
        return ParsedPreferences(
            sorted(set(unavailable)),
            sorted(set(prefer)),
            sorted(set(avoid)),
            avoid_weekends,
            question,
        )


MONTHS_DE = [
    "januar",
    "februar",
    "märz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
]
MONTHS_EN = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]


class CopilotStandIn(Copilot):
    """C8 stand-in: templated answers for weekend and hours questions, citing the rule version.

    No LLM, no tools, no publish or approve capability.
    """

    info = EngineInfo(
        "C8",
        "stand-in",
        STANDIN_VERSION,
        "Templated answers for weekend and hours questions; LangGraph agent in phase 10.",
        10,
    )

    def ask(self, question: str, language: str, facts: CopilotFacts) -> CopilotAnswer:
        """Answer from the facts provided."""
        q = question.lower()
        person = next(
            (sid for sid, name in facts.staff_names.items() if name.lower().split()[-1] in q), None
        )
        month = facts.default_month
        for i, (de, en) in enumerate(zip(MONTHS_DE, MONTHS_EN, strict=True)):
            if de in q or en in q:
                candidate = date(facts.default_month.year, i + 1, 1)
                month = (
                    candidate
                    if candidate in facts.planned_months or i + 1 >= 10
                    else date(facts.default_month.year + 1, i + 1, 1)
                )
                break
        de_lang = language == "de"
        rule = (
            f"Regelversion {facts.rule_version}"
            if de_lang
            else f"rule version {facts.rule_version}"
        )
        if person is None or not any(w in q for w in ("wochenende", "weekend", "stunden", "hours")):
            return CopilotAnswer(
                "Diese Frage kann der Platzhalter-Copilot noch nicht beantworten."
                if de_lang
                else "The stand-in copilot cannot answer this question yet.",
                {},
                [],
                False,
            )
        name = facts.staff_names[person]
        month_label = (
            f"{MONTHS_DE[month.month - 1].capitalize()} {month.year}"
            if de_lang
            else f"{MONTHS_EN[month.month - 1].capitalize()} {month.year}"
        )
        if month not in facts.planned_months:
            text = (
                f"{month_label} ist noch nicht geplant. Laut {rule} sind höchstens "
                f"{facts.rules['max_weekends_per_month']} Wochenenden pro Monat erlaubt."
                if de_lang
                else f"{month_label} is not planned yet. Under {rule}, at most "
                f"{facts.rules['max_weekends_per_month']} weekends per month are allowed."
            )
            return CopilotAnswer(
                text,
                {"max_weekends_per_month": facts.rules["max_weekends_per_month"]},
                [f"max_weekends_per_month ({facts.rule_version})"],
                True,
            )
        if "stunden" in q or "hours" in q:
            hours = facts.hours_per_month.get((person, month), 0.0)
            text = (
                f"{name} hat im {month_label} {hours:g} angerechnete Stunden geplant."
                if de_lang
                else f"{name} has {hours:g} credited hours planned in {month_label}."
            )
            return CopilotAnswer(text, {"hours": hours}, [], True)
        n = facts.weekends_per_month.get((person, month), 0)
        limit = facts.rules["max_weekends_per_month"]
        text = (
            f"{name} hat im {month_label} {n} Wochenenden mit Dienst."
            f" Erlaubt sind laut {rule} höchstens {limit}."
            if de_lang
            else f"{name} has duty on {n} weekends in {month_label}."
            f" Under {rule}, at most {limit} are allowed."
        )
        return CopilotAnswer(
            text,
            {"weekends": n, "max_weekends_per_month": limit},
            [f"max_weekends_per_month ({facts.rule_version})"],
            True,
        )
