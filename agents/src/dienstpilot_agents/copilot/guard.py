"""The privacy boundary of C8: people become aliases on the way out and names come back on display.

* ``Aliases`` turns every staff id and every name (full name, or surname when it is unique) in text
  and in tool results into ``P1``, ``P2`` ... and back. The map lives in the API process only; it
  is the same for every call of a run (sorted by id, so recordings are reproducible).
* ``untrusted`` wraps free text written by a person in delimiters with a code derived from the text.
* ``scan`` is the test every outbound request passes: no display name, no surname, no person id,
  no persona key, no health word. A finding is a failure, not a warning.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Any

UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
ALIAS = re.compile(r"\bP(\d{1,3})\b")
HEALTH = re.compile(r"krank|erkrank|diagnos|sick|illness|\bill\b|arbeitsunfähig", re.IGNORECASE)
TITLES = re.compile(r"^(?:Prof\.\s+)?Dr\.\s+")
UNKNOWN = "[unbekannte Person]"
FREE_TEXT_KEYS = ("reason", "title", "body")


def _surname(display_name: str) -> str:
    return TITLES.sub("", display_name).split()[-1]


@dataclass(frozen=True)
class Finding:
    """Something that must not leave the process."""

    kind: str
    what: str


class Aliases:
    """Staff ids and names to aliases and back, for one department."""

    def __init__(self, staff: dict[str, str]) -> None:
        """``staff`` maps staff id to display name."""
        self.ids = sorted(staff)
        self.alias_of = {sid: f"P{i + 1}" for i, sid in enumerate(self.ids)}
        self.id_of = {a: sid for sid, a in self.alias_of.items()}
        self.names = dict(staff)
        surnames: dict[str, list[str]] = {}
        for sid, name in staff.items():
            surnames.setdefault(_surname(name), []).append(sid)
        self._unique = {s: ids[0] for s, ids in surnames.items() if len(ids) == 1}
        self._ambiguous = {s for s, ids in surnames.items() if len(ids) > 1}

    def to_model(self, text: str) -> str:
        """Replace ids and names with aliases (an ambiguous surname becomes a neutral phrase)."""
        text = UUID.sub(lambda m: self.alias_of.get(m.group(0), m.group(0)), text)
        for sid, name in sorted(self.names.items(), key=lambda kv: -len(kv[1])):
            text = text.replace(name, self.alias_of[sid])
            bare = TITLES.sub("", name)
            text = re.sub(rf"(?<!\w){re.escape(bare)}(?!\w)", self.alias_of[sid], text)
        for surname, sid in self._unique.items():
            text = re.sub(
                rf"(?:Dr\.\s+)?(?<!\w){re.escape(surname)}(?!\w)", self.alias_of[sid], text
            )
        for surname in self._ambiguous:
            text = re.sub(rf"(?:Dr\.\s+)?(?<!\w){re.escape(surname)}(?!\w)", UNKNOWN, text)
        return text

    def from_model(self, text: str) -> str:
        """Put names back for display (aliases that name nobody stay as they are)."""
        return ALIAS.sub(lambda m: self.names.get(self.id_of.get(m.group(0), ""), m.group(0)), text)

    def ids_in(self, value: Any) -> Any:
        """Map aliases to ids inside tool arguments (any nesting)."""
        if isinstance(value, str):
            return self.id_of.get(value, value)
        if isinstance(value, list):
            return [self.ids_in(v) for v in value]
        if isinstance(value, dict):
            return {k: self.ids_in(v) for k, v in value.items()}
        return value

    def alias_json(self, value: Any) -> Any:
        """Map ids and names to aliases inside a tool result (any nesting)."""
        if isinstance(value, str):
            return self.to_model(value)
        if isinstance(value, list):
            return [self.alias_json(v) for v in value]
        if isinstance(value, dict):
            return {k: self.alias_json(v) for k, v in value.items()}
        return value

    def findings(
        self, text: str, persona_keys: tuple[str, ...] = (), *, health: bool = True
    ) -> list[Finding]:
        """Return everything in ``text`` that must not leave: names, surnames, ids, keys, health."""
        out: list[Finding] = []
        for sid, name in self.names.items():
            if name in text:
                out.append(Finding("name", name))
            if sid in text:
                out.append(Finding("person-id", sid))
        for surname in {_surname(n) for n in self.names.values()}:
            if re.search(rf"(?<!\w){re.escape(surname)}(?!\w)", text):
                out.append(Finding("surname", surname))
        for key in persona_keys:
            if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text, re.IGNORECASE):
                out.append(Finding("persona-key", key))
        for m in HEALTH.finditer(text if health else ""):
            out.append(Finding("health-word", m.group(0)))
        return out


def code_for(text: str) -> str:
    """Return a delimiter code the text cannot contain: it is derived from the text itself."""
    return hashlib.sha256(text.encode()).hexdigest()[:10].upper()


def untrusted(text: str) -> str:
    """Wrap free text written by a person: the model is told that this is data, never orders."""
    code = code_for(text)
    return f"<<<DATA-{code}>>>\n{text}\n<<<END-{code}>>>"


def delimit_free_text(value: Any) -> Any:
    """Wrap every free-text field (reason, title, body) of a tool result in delimiters."""
    if isinstance(value, list):
        return [delimit_free_text(v) for v in value]
    if isinstance(value, dict):
        return {
            k: untrusted(v)
            if k in FREE_TEXT_KEYS and isinstance(v, str) and v
            else delimit_free_text(v)
            for k, v in value.items()
        }
    return value
