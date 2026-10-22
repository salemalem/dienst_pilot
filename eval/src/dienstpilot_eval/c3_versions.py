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
C5_RULE = REPO / "ml" / "cover_ranker" / "PROMOTION_RULE.md"
C5_CHAMPION_DIR = REPO / "ml" / "cover_ranker" / "artifacts" / "champion"
C5_PATHS = ("cover_ranker/", "features/cover.py", "training/c5")
C6_RULE = REPO / "ml" / "leave_surrogate" / "PROMOTION_RULE.md"
C6_CHAMPION_DIR = REPO / "ml" / "leave_surrogate" / "artifacts" / "champion"
C6_PATHS = ("leave_surrogate/", "features/leave.py", "training/c6")


def is_c4(rel: str) -> bool:
    """Return whether a source path (relative to the package) belongs to C4."""
    return rel.startswith(C4_PATHS)


def is_c5(rel: str) -> bool:
    """Return whether a source path (relative to the package) belongs to C5."""
    return rel.startswith(C5_PATHS)


def is_c6(rel: str) -> bool:
    """Return whether a source path (relative to the package) belongs to C6."""
    return rel.startswith(C6_PATHS)


def _sources_sha256(component: str) -> str:
    h = hashlib.sha256()
    for f in sorted(ML_SOURCES.rglob("*.py")):
        rel = str(f.relative_to(ML_SOURCES))
        belongs = "c4" if is_c4(rel) else "c5" if is_c5(rel) else "c6" if is_c6(rel) else "c3"
        if belongs != component:
            continue
        h.update(str(f.relative_to(ML_SOURCES)).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def ml_sources_sha256() -> str:
    """Return one hash over the C3 source code (every .py file of the ML package except C4's)."""
    return _sources_sha256("c3")


def c4_sources_sha256() -> str:
    """Return one hash over the C4 source code (see ``C4_PATHS``)."""
    return _sources_sha256("c4")


def sha256_file(path: Path) -> str:
    """Return the sha256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def c5_sources_sha256() -> str:
    """Return one hash over the C5 source code (see ``C5_PATHS``)."""
    return _sources_sha256("c5")


def c6_sources_sha256() -> str:
    """Return one hash over the C6 source code (see ``C6_PATHS``)."""
    return _sources_sha256("c6")
