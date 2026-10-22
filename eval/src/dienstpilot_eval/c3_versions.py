"""What a committed C3 result belongs to: the source code, the rule file and the served bundle."""

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RULE = REPO / "ml" / "absence_forecast" / "PROMOTION_RULE.md"
CHAMPION_DIR = REPO / "ml" / "absence_forecast" / "artifacts" / "champion"
C4_RULE = REPO / "ml" / "preference_learner" / "PROMOTION_RULE.md"
C4_CHAMPION_DIR = REPO / "ml" / "preference_learner" / "artifacts" / "champion"
ML_SOURCES = REPO / "ml" / "src" / "dienstpilot_ml"


C4_PATHS = ("preference_learner/", "features/preference.py", "training/c4")


def is_c4(rel: str) -> bool:
    """Return whether a source path (relative to the package) belongs to C4."""
    return rel.startswith(C4_PATHS)


def _sources_sha256(want_c4: bool) -> str:
    h = hashlib.sha256()
    for f in sorted(ML_SOURCES.rglob("*.py")):
        if is_c4(str(f.relative_to(ML_SOURCES))) != want_c4:
            continue
        h.update(str(f.relative_to(ML_SOURCES)).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def ml_sources_sha256() -> str:
    """Return one hash over the C3 source code (every .py file of the ML package except C4's)."""
    return _sources_sha256(False)


def c4_sources_sha256() -> str:
    """Return one hash over the C4 source code (see ``C4_PATHS``)."""
    return _sources_sha256(True)


def sha256_file(path: Path) -> str:
    """Return the sha256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
