from pathlib import Path

import pytest

from synthdata.cli import main
from synthdata.config import DEFAULT_SEED


@pytest.fixture(scope="session")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One full generation with the default seed, shared by the tests."""
    out = tmp_path_factory.mktemp("synthetic") / "v1"
    assert main(["generate", "--seed", str(DEFAULT_SEED), "--out", str(out)]) == 0
    return out
