"""Event schemas: versioned JSON Schema files in ``schemas/<EventType>.v<N>.json``.

A published schema file never changes: a breaking change is a new file with the next version,
and both are consumed while consumers migrate (ARCHITECTURE §8). ``MANIFEST.json`` pins the
SHA-256 of every file, and a contract test fails when a file differs from its pin.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

DIR = Path(__file__).parent / "schemas"
_NAME = re.compile(r"^(?P<type>[A-Za-z]+)\.v(?P<v>\d+)\.json$")


class UnknownEventError(KeyError):
    """No schema is registered for this event type and version."""


@lru_cache
def load() -> dict[tuple[str, int], dict[str, Any]]:
    """Return every schema, keyed by (event type, version)."""
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for path in sorted(DIR.glob("*.json")):
        m = _NAME.match(path.name)
        if m:
            out[(m["type"], int(m["v"]))] = json.loads(path.read_text(encoding="utf-8"))
    return out


def latest(event_type: str) -> int:
    """Return the newest version of an event type."""
    versions = [v for (t, v) in load() if t == event_type]
    if not versions:
        raise UnknownEventError(event_type)
    return max(versions)


def validate(event_type: str, version: int, payload: dict[str, Any]) -> None:
    """Raise ``jsonschema.ValidationError`` unless the payload fits the schema."""
    try:
        schema = load()[(event_type, version)]
    except KeyError as e:
        raise UnknownEventError(f"{event_type} v{version}") from e
    jsonschema.validate(payload, schema, format_checker=jsonschema.FormatChecker())
