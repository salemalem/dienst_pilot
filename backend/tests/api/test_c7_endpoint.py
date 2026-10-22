"""The M4 parse endpoint with the language model engine (scripted client; plumbing only)."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dienstpilot.app.deps import get_engines

from .test_c7_intake import EMPTY, Scripted, _intake, _staff_names

pytestmark = pytest.mark.db


def test_the_wishes_endpoint_sends_only_the_text_the_month_and_the_language(
    client: Any, login: Any, seed_dir: Path
) -> None:
    fake = Scripted({**EMPTY, "unavailable": ["2026-12-07"]})
    engines = get_engines()
    client.app.dependency_overrides[get_engines] = lambda: replace(engines, intake=_intake(fake))
    r = client.post(
        "/me/wishes/parse",
        json={"text": "Am 7.12. kann ich nicht.", "language": "de"},
        headers=login("kaya"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unavailable"] == ["2026-12-07"] and body["ai_generated"] is True
    assert body["engine"]["implementation"] == "built" and body["replayed"] is False
    sent = json.dumps(fake.requests[0].canonical(), ensure_ascii=False)
    assert not [n for n in _staff_names(seed_dir) if n in sent]
    assert "kaya" not in sent.lower()
