import importlib

import pytest

CONTEXTS = [
    "identity",
    "organization",
    "requests",
    "planning",
    "operations",
    "fairness",
    "notifications",
    "audit",
    "shared",
    "shared.ports",
    "shared.events",
    "shared.settings",
]


@pytest.mark.parametrize("name", CONTEXTS)
def test_context_is_importable(name: str) -> None:
    assert importlib.import_module(f"dienstpilot.{name}") is not None


def test_llm_models_are_configuration() -> None:
    from dienstpilot.shared.settings import Settings

    settings = Settings(llm_model_intake="model-a", llm_model_copilot="model-b")
    assert (settings.llm_model_intake, settings.llm_model_copilot) == ("model-a", "model-b")
