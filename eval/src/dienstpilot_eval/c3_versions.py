"""What a committed C3 result belongs to: the source code, the rule file and the served bundle."""

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RULE = REPO / "ml" / "absence_forecast" / "PROMOTION_RULE.md"
CHAMPION_DIR = REPO / "ml" / "absence_forecast" / "artifacts" / "champion"
ML_SOURCES = REPO / "ml" / "src" / "dienstpilot_ml"


def ml_sources_sha256() -> str:
    """Return one hash over the C3 source code (every .py file under ml/src/dienstpilot_ml)."""
    h = hashlib.sha256()
    for f in sorted(ML_SOURCES.rglob("*.py")):
        h.update(str(f.relative_to(ML_SOURCES)).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    """Return the sha256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
