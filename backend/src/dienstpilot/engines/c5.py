"""C5: the cover ranker, served from the committed champion bundle.

The model (``ml/cover_ranker/artifacts/champion/``) is chosen by ``eval/run_c5_eval.py`` under
``ml/cover_ranker/PROMOTION_RULE.md``. The ordering policy is separate from the model: candidates
(already checked by C2) are bucketed by cover burden, least burdened first, and P(accept) orders
people only within a bucket. The probability never leaves this class: it is not part of the port's
output, so no API response can show it.
"""

import json
import os
from pathlib import Path

import dienstpilot_ml
from dienstpilot.shared.ports import CoverCandidate, CoverRanker, EngineInfo
from dienstpilot_ml.cover_ranker.models import Bundle, bundle_sha256, load_bundle
from dienstpilot_ml.cover_ranker.policy import BUCKET_WIDTH, Ranked, order
from dienstpilot_ml.features.cover import CoverFeatures, matrix

ML_ROOT = Path(dienstpilot_ml.__file__).resolve().parents[2]
BUNDLE_DIR = ML_ROOT / "cover_ranker" / "artifacts" / "champion"
RESULT = ML_ROOT.parent / "eval" / "results" / "c5.json"
NAMES = {
    "base_rate": "base rate (no personal or situational signal)",
    "logistic": "logistic regression",
    "lightgbm": "LightGBM with isotonic calibration",
}


def _info(bundle: Bundle, sha: str) -> EngineInfo:
    kind = bundle.kind
    note = (
        f"Burden buckets of {BUCKET_WIDTH} covers (last 90 days), least burdened first; inside a "
        f"bucket ordered by P(accept) from the C5 champion: {NAMES[kind]}, fitted on 2021-2024."
    )
    if RESULT.exists():
        doc = json.loads(RESULT.read_text(encoding="utf-8"))
        if not doc["champion"]["promoted_learner"]:
            note += " The LightGBM learner did not pass the pre-registered promotion rule."
        test = doc.get("test_2025", {}).get(kind)
        if test:
            note += (
                f" 2025 held-out Brier score {test['brier']:.4f}, AUC {test['auc']:.3f}"
                " (eval/results/c5.json)."
            )
    return EngineInfo("C5", "built", f"{bundle.meta['c5_version']}-{kind}-{sha[:8]}", note, None)


class C5CoverRanker(CoverRanker):
    """Orders eligible colleagues for a cover request; the Planner and the cascade use the order."""

    def __init__(self, bundle_dir: Path | None = None) -> None:
        """Load the champion bundle (``C5_BUNDLE_DIR`` or the committed one)."""
        path = bundle_dir or Path(os.environ.get("C5_BUNDLE_DIR", BUNDLE_DIR))
        self.bundle = load_bundle(path)
        self.info = _info(self.bundle, bundle_sha256(path))

    def rank(self, candidates: list[CoverCandidate]) -> list[CoverCandidate]:
        """Return the candidates in asking order (bucket, then P(accept), then ties)."""
        if not candidates:
            return []
        probs = self.bundle.predict(
            matrix(
                CoverFeatures(
                    c.hours_ratio,
                    c.days_since_last_cover,
                    c.shifts_last_7d,
                    c.notice_hours,
                    c.shift_type,
                    c.weekday,
                    c.request_hour,
                    c.confirmed_pref,
                )
                for c in candidates
            )
        )
        by_id = {c.staff_id: c for c in candidates}
        ranked = [
            Ranked(c.staff_id, c.covers_last_90_days, c.hours_ratio, float(p))
            for c, p in zip(candidates, probs, strict=True)
        ]
        return [by_id[r.staff_id] for r in order(ranked)]
