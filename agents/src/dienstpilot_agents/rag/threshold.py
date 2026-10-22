"""The frozen "no source" threshold written by ``eval/run_rag_eval.py`` (chosen on dev data)."""

import json
from functools import lru_cache

from dienstpilot_agents.rag.corpus import CORPUS_DIR

PATH = CORPUS_DIR.parent / "threshold.json"


@lru_cache
def no_source_cosine() -> float | None:
    """Return tau, or None when the evaluation has not been run (then no threshold is applied)."""
    if not PATH.exists():
        return None
    return float(json.loads(PATH.read_text())["tau"])
