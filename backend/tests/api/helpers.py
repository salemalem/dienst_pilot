from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from dienstpilot.shared.settings import DEMO_NOW


def future_shift(
    client: TestClient,
    headers: dict[str, str],
    month: str = "2026-11",
    kinds: tuple[str, ...] = ("frueh", "spaet", "nacht", "bereitschaft"),
) -> dict[str, Any]:
    """Return a future shift of the signed-in physician."""
    days = client.get(f"/me/roster?month={month}", headers=headers).json()["days"]
    for d in days:
        for s in d["shifts"]:
            if s["shift_type"] in kinds and date.fromisoformat(s["date"]) > DEMO_NOW.date():
                return dict(s)
    raise AssertionError("no future shift")


def coverable_shift(
    client: TestClient,
    headers: dict[str, str],
    month: str = "2026-11",
    kinds: tuple[str, ...] = ("frueh", "spaet", "nacht", "bereitschaft"),
    free_to_give: bool = False,
) -> dict[str, Any]:
    """Return a future shift of the signed-in physician that a colleague could take (C2).

    ``free_to_give``: giving it away also breaks no rule for the physician (e.g. hours band).
    """
    days = client.get(f"/me/roster?month={month}", headers=headers).json()["days"]
    for d in days:
        for s in d["shifts"]:
            if s["shift_type"] in kinds and date.fromisoformat(s["date"]) > DEMO_NOW.date():
                a = client.get(
                    f"/me/swaps/audience?assignment_id={s['assignment_id']}", headers=headers
                ).json()
                if a["eligible_colleagues"] and not (free_to_give and a["needs_planner"]):
                    return dict(s)
    raise AssertionError("no coverable future shift")


def walk(obj: Any) -> list[tuple[str | None, Any]]:
    """Return every (key, value) pair in a JSON document."""
    out: list[tuple[str | None, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append((k, v))
            out += walk(v)
    elif isinstance(obj, list):
        for v in obj:
            out.append((None, v))
            out += walk(v)
    return out
