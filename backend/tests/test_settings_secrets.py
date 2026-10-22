"""The Anthropic key is read from the environment or the git-ignored .env, and never shown."""

import subprocess
from pathlib import Path

import pytest

from dienstpilot.shared.settings import Settings

REPO = Path(__file__).resolve().parents[2]


def test_the_key_comes_from_a_dotenv_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test-123\nLLM_MODEL_INTAKE=x\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings()
    assert (
        s.anthropic_api_key is not None and s.anthropic_api_key.get_secret_value() == "sk-test-123"
    )
    assert "sk-test-123" not in repr(s) and "sk-test-123" not in str(s.model_dump())


def test_the_environment_wins_and_no_key_means_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if (REPO / ".env").exists() and "ANTHROPIC_API_KEY" in (REPO / ".env").read_text():
        pytest.skip("this machine has a key in the repository .env")
    assert Settings().anthropic_api_key is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert Settings().anthropic_api_key.get_secret_value() == "sk-env"  # type: ignore[union-attr]


def test_dotenv_is_git_ignored_and_no_key_is_committed() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", ".env"], cwd=REPO, capture_output=True, text=True, check=False
    )
    assert ignored.returncode == 0, ".env must be git-ignored"
    tracked = subprocess.run(
        ["git", "grep", "-l", "-E", "sk-ant-[A-Za-z0-9_-]{10,}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.stdout.strip() == "", "a key-shaped string is committed"
