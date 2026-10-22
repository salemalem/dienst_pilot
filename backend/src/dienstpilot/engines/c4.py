"""C4: the preference learner, served from the committed champion bundle.

The bundle (``ml/preference_learner/artifacts/champion/``) is written by ``eval/run_c4_eval.py``
when the promotion rule has picked the champion. It holds department-level numbers only. The
person's own counts come with each request and are never stored: this class keeps no state.
Serving needs only numpy; MLflow and the training stack are never imported here.
"""

import json
import os
from datetime import date
from pathlib import Path

import dienstpilot_ml
from dienstpilot.shared.ports import (
    EngineInfo,
    PreferenceContext,
    PreferenceLearner,
    PreferenceSuggestion,
)
from dienstpilot_ml.features.preference import (
    avoid_opportunities,
    event_counts,
    wish_opportunities,
)
from dienstpilot_ml.preference_learner.models import (
    Bundle,
    bundle_sha256,
    load_bundle,
    suggest,
)

ML_ROOT = Path(dienstpilot_ml.__file__).resolve().parents[2]
BUNDLE_DIR = ML_ROOT / "preference_learner" / "artifacts" / "champion"
RESULT = ML_ROOT.parent / "eval" / "results" / "c4.json"
NAMES = {
    "pooled": "pooled department rates",
    "raw": "raw per-person rates",
    "hierarchical": "hierarchical Beta-Binomial",
}


def _info(bundle: Bundle, sha: str) -> EngineInfo:
    kind = bundle.kind
    note = f"Champion of the C4 registry: {NAMES[kind]}, fitted on 2021-2024."
    if RESULT.exists():
        doc = json.loads(RESULT.read_text(encoding="utf-8"))
        if not doc["champion"]["promoted_learner"]:
            note += " The hierarchical learner did not pass the pre-registered promotion rule."
        test = doc.get("test_2025", {}).get(kind)
        if test:
            note += (
                " 2025 held-out log-likelihood per opportunity:"
                f" wishes {test['wish']['mean_ll']:.4f},"
                f" swaps {test['avoid']['mean_ll']:.4f} (eval/results/c4.json)."
            )
    return EngineInfo("C4", "built", f"{bundle.meta['c4_version']}-{kind}-{sha[:8]}", note, None)


class C4PreferenceLearner(PreferenceLearner):
    """Suggests preferences from one person's own history; every suggestion is confirmed by them."""

    def __init__(self, bundle_dir: Path | None = None) -> None:
        """Load the champion bundle (``C4_BUNDLE_DIR`` or the committed one)."""
        path = bundle_dir or Path(os.environ.get("C4_BUNDLE_DIR", BUNDLE_DIR))
        self.bundle = load_bundle(path)
        self.info = _info(self.bundle, bundle_sha256(path))

    def suggest(
        self,
        wishes: list[tuple[date, str | None]],
        swapped_away: list[tuple[date, str]],
        context: PreferenceContext,
    ) -> list[PreferenceSuggestion]:
        """Return at most three suggestions under the display policy of the promotion rule."""
        found = suggest(
            self.bundle,
            event_counts(wishes),
            wish_opportunities(context.answered_months, context.unavailable_days),
            event_counts(swapped_away),
            avoid_opportunities(context.assigned),
        )
        return [
            PreferenceSuggestion(
                s.kind,
                s.weekday,
                s.shift_type,
                s.events,
                s.trials,
                round(s.rate, 4),
                round(s.department_rate, 4),
                round(s.probability, 2),
            )
            for s in found
        ]
