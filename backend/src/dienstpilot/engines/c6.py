"""C6: the instant leave hint, served from the committed champion bundle.

The model (``ml/leave_surrogate/artifacts/champion/``) is chosen by ``eval/run_c6_eval.py`` under
``ml/leave_surrogate/PROMOTION_RULE.md``. The hint is advisory: the incremental solver check
(C1 with C2) answers within seconds and the screen shows its answer. A request over two months
was never labelled, so it gets the stand-in rule instead of the model.
"""

import json
import os
from pathlib import Path

import dienstpilot_ml
from dienstpilot.shared.ports import EngineInfo, LeaveFacts, LeaveFeasibility, LeaveHint
from dienstpilot_ml.features.leave import FEATURES, features, matrix
from dienstpilot_ml.leave_surrogate.models import (
    STAND_IN_LIMIT,
    Bundle,
    bundle_sha256,
    load_bundle,
)

ML_ROOT = Path(dienstpilot_ml.__file__).resolve().parents[2]
BUNDLE_DIR = ML_ROOT / "leave_surrogate" / "artifacts" / "champion"
RESULT = ML_ROOT.parent / "eval" / "results" / "c6.json"
NAMES = {
    "stand_in": "the previous rule (approved leave per day against the concurrency limit)",
    "logistic": "logistic regression",
    "lightgbm": "LightGBM",
}
APPROVED_MAX = FEATURES.index("approved_max")


def _pct(v: float) -> str:
    return f"{100 * v:.1f} %"


def _info(bundle: Bundle, sha: str) -> EngineInfo:
    kind = bundle.kind
    note = (
        f"Instant hint from the C6 champion: {NAMES[kind]}, trained on solver answers for "
        "simulated requests, 2021-2024. Advisory only: the solver's answer is the one shown."
    )
    if RESULT.exists():
        doc = json.loads(RESULT.read_text(encoding="utf-8"))
        if not doc["champion"]["promoted_learner"]:
            note += " The LightGBM learner did not pass the pre-registered promotion rule."
        t = doc.get("test_2025", {}).get(kind)
        if t:
            nat, stress, pooled = t["natural"], t["stress"], t["pooled"]
            note += (
                f" 2025 held-out, precision of a yes: natural states {_pct(nat['precision'])}, "
                f"simulated stress states {_pct(stress['precision'])}, "
                f"pooled including simulated stress states {_pct(pooled['precision'])} "
                "(eval/results/c6.json)."
            )
    version = bundle.meta.get("c6_version", "0")
    return EngineInfo("C6", "built", f"{version}-{kind}-{sha[:8]}", note, None)


class C6LeaveFeasibility(LeaveFeasibility):
    """Gives the instant hint on M5; the solver's check confirms or overrides it."""

    def __init__(self, bundle_dir: Path | None = None) -> None:
        """Load the champion bundle (``C6_BUNDLE_DIR`` or the committed one)."""
        path = bundle_dir or Path(os.environ.get("C6_BUNDLE_DIR", BUNDLE_DIR))
        self.bundle = load_bundle(path)
        self.info = _info(self.bundle, bundle_sha256(path))
        self._rule = Bundle("stand_in", {"model": "stand_in"})

    def hint(self, facts: LeaveFacts, limit: int) -> LeaveHint:
        """Return the hint for the window (the stand-in rule if it spans two months)."""
        x = matrix([features(facts)])
        same_month = (facts.start.year, facts.start.month) == (facts.end.year, facts.end.month)
        used = self.bundle if same_month else self._rule
        outcome = used.hint(x)[0]
        return LeaveHint(
            outcome,  # type: ignore[arg-type]
            int(x[0, APPROVED_MAX]),
            limit if limit else STAND_IN_LIMIT,
            facts.overlapping,
            "model" if used is self.bundle and used.kind != "stand_in" else "rule",
        )
