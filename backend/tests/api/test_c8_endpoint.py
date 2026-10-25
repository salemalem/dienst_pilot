"""The copilot endpoint: stand-in at once, the agent as a job, only where the gates released it."""

import json
from dataclasses import replace
from typing import Any

import pytest

from dienstpilot.app.deps import get_engines
from dienstpilot.engines.c8 import C8Copilot, capability, champion
from dienstpilot.engines.standins import CopilotStandIn
from dienstpilot.shared.settings import Settings
from dienstpilot_agents.copilot.outcome import Outcome

pytestmark = pytest.mark.db
WHATIF_DE = (
    "Was passiert, wenn Dr. Jonas Weber den Nachtdienst am 12.11.2026 an Dr. Lea Lorenz abgibt?"
)
WHATIF_EN = "What if Dr. Jonas Weber hands the night shift on 12 November 2026 to Dr. Lea Lorenz?"
SERVED = {
    "served": {"lookups": False, "rules": False, "whatifs": True, "drafting": True},
    "safety_pass": True,
}


class Fake:
    """Stands in for the agent: records what it was given and returns a fixed outcome."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kw: Any) -> Outcome:
        self.calls.append(kw)
        return Outcome(
            "Nein, nicht regelkonform.",
            False,
            None,
            [{"tool": "run_what_if", "label": "Was-wäre-wenn", "args": {"month": "2026-11"}}],
            {
                "valid": False,
                "violations": [{"rule": "min_rest", "date": "2026-11-12", "person": None}],
                "uncovered": [],
                "validator_version": "c2",
            },
        )


def _use(
    client: Any, factory: Any, verdict: dict[str, Any] | None, fake: Fake | None = None
) -> Fake:
    f = fake or Fake()
    engines = get_engines()
    copilot = C8Copilot(CopilotStandIn(), verdict, Settings(), None, False, runner=f)
    swapped = replace(engines, copilot=copilot)
    client.app.dependency_overrides[get_engines] = lambda: swapped
    factory.queue.engines = swapped  # the inline job reads its engines from the queue
    return f


def test_the_gates_decide_which_questions_the_agent_may_see() -> None:
    assert capability("Was passiert, wenn Dr. A den Nachtdienst an Dr. B abgibt?") == "whatifs"
    assert capability("Formuliere eine Begründung für die Änderung") == "drafting"
    assert capability("Wie viele Nachtdienste hat Dr. A im November?") is None
    assert capability("Veröffentliche den Dienstplan jetzt.") is None
    v = champion()
    assert v is not None and v["served"]["lookups"] is False and v["served"]["rules"] is False


def test_a_lookup_is_answered_by_the_stand_in_at_once_and_says_so(
    client: Any, app_factory: Any, login: Any
) -> None:
    fake = _use(client, app_factory, SERVED)
    r = client.post(
        "/copilot/ask",
        json={
            "question": "Wie viele Wochenenden hat Dr. Jonas Weber im Oktober?",
            "language": "de",
        },
        headers=login("brandt"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done" and body["ai_generated"] is False
    assert body["engine"]["implementation"] == "stand-in" and fake.calls == []


def test_a_what_if_goes_to_the_agent_as_a_job_and_can_be_polled(
    client: Any, app_factory: Any, login: Any
) -> None:
    fake = _use(client, app_factory, SERVED)
    h = login("brandt")
    r = client.post(
        "/copilot/ask",
        json={
            "question": WHATIF_DE,
            "language": "de",
        },
        headers=h,
    )
    assert r.status_code in (200, 202), r.text  # the test queue runs the job inline
    body = r.json()
    assert body["ai_generated"] is True and body["run_id"]
    polled = client.get(f"/copilot/runs/{body['run_id']}", headers=h).json()
    assert polled["status"] == "done", polled
    assert polled["what_if"]["valid"] is False, polled
    assert polled["sources"][0]["tool"] == "run_what_if"
    # the agent got the signed-in user's own token and role, and the staff list for aliases
    call = fake.calls[0]
    assert call["role"] == "planner" and call["token"] == h["Authorization"].split(" ", 1)[1]
    assert "Dr. Jonas Weber" in call["staff"].values()


def test_a_failed_agent_run_is_reported_not_hung(client: Any, app_factory: Any, login: Any) -> None:
    class Boom(Fake):
        async def __call__(self, **kw: Any) -> Outcome:
            raise RuntimeError("model down")

    _use(client, app_factory, SERVED, Boom())
    h = login("brandt")
    r = client.post(
        "/copilot/ask",
        json={
            "question": WHATIF_EN,
            "language": "en",
        },
        headers=h,
    )
    polled = client.get(f"/copilot/runs/{r.json()['run_id']}", headers=h).json()
    assert polled["status"] == "failed"


def test_without_passed_gates_or_without_safety_the_stand_in_answers_everything(
    client: Any, app_factory: Any, login: Any
) -> None:
    for verdict in (
        None,
        {**SERVED, "safety_pass": False},
        {"served": {"whatifs": False, "drafting": False}, "safety_pass": True},
    ):
        fake = _use(client, app_factory, verdict)
        r = client.post(
            "/copilot/ask",
            json={
                "question": WHATIF_EN,
                "language": "en",
            },
            headers=login("brandt"),
        )
        assert r.status_code == 200 and r.json()["ai_generated"] is False and fake.calls == []


def test_only_the_asker_can_read_a_run_and_oversight_gets_no_draft_tool(
    client: Any, app_factory: Any, login: Any
) -> None:
    _use(client, app_factory, SERVED)
    r = client.post(
        "/copilot/ask",
        json={
            "question": WHATIF_DE,
            "language": "de",
        },
        headers=login("brandt"),
    )
    assert (
        client.get(f"/copilot/runs/{r.json()['run_id']}", headers=login("hoffmann")).status_code
        == 404
    )
    assert (
        client.get(f"/copilot/runs/{r.json()['run_id']}", headers=login("kaya")).status_code == 403
    )
    d = client.post(
        "/copilot/ask",
        json={"question": "Entwirf eine Ankündigung an alle.", "language": "de"},
        headers=login("vogel"),
    )
    assert d.json()["ai_generated"] is False  # drafting is for the Planner only
    s = json.dumps(d.json())
    assert "token" not in s.lower()
