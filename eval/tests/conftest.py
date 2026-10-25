import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from dienstpilot_eval.inputs import Data

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def seed_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The synthetic dataset: DIENSTPILOT_SEED_DIR, else a fresh generation."""
    given = os.environ.get("DIENSTPILOT_SEED_DIR")
    if given:
        return Path(given)
    out = tmp_path_factory.mktemp("seed") / "v1"
    subprocess.run([sys.executable, "-m", "synthdata", "generate", "--out", str(out)], check=True, cwd=REPO)
    return out


@pytest.fixture(scope="session")
def data(seed_root: Path) -> Data:
    return Data(seed_root)


@pytest.fixture(scope="session")
def checker() -> ModuleType:
    """The Phase 2 test-only checker (synthdata/tests/hard_rules.py), the independent second key."""
    path = REPO / "synthdata" / "tests" / "hard_rules.py"
    spec = importlib.util.spec_from_file_location("hard_rules", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["hard_rules"] = module
    spec.loader.exec_module(module)
    return module
