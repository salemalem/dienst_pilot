"""C3: the absence forecaster, served from the committed champion bundle.

The bundle (``ml/absence_forecast/artifacts/champion/``) is written by ``eval/run_c3_eval.py`` when
the promotion rule has picked the champion. Serving needs only numpy and LightGBM: MLflow and
the training stack are never imported here (an import-linter contract checks it).
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import dienstpilot_ml
from dienstpilot.shared.ports import (
    AbsenceForecast,
    AbsenceForecaster,
    EngineInfo,
    ForecastContext,
)
from dienstpilot_ml.absence_forecast.models import Bundle, bundle_sha256, load_bundle
from dienstpilot_ml.features.absence import (
    HORIZONS,
    SERIES_START,
    Calendar,
    FeatureBuilder,
    daily_counts,
)

ML_ROOT = Path(dienstpilot_ml.__file__).resolve().parents[2]
BUNDLE_DIR = ML_ROOT / "absence_forecast" / "artifacts" / "champion"
RESULT = ML_ROOT.parent / "eval" / "results" / "c3.json"


def _info(bundle: Bundle, sha: str) -> EngineInfo:
    kind = bundle.model.kind
    note = f"Champion '{kind}' of the C3 registry, trained on 2021-2024."
    if RESULT.exists():
        test = json.loads(RESULT.read_text(encoding="utf-8")).get("test_2025", {}).get(kind)
        if test:
            note += (
                f" 2025 test: MAE {test['mae']:.2f}, 80 % interval coverage"
                f" {test['coverage_80']:.0%} (eval/results/c3.json)."
            )
    return EngineInfo("C3", "built", f"{bundle.meta['c3_version']}-{kind}-{sha[:8]}", note, None)


class C3Forecaster(AbsenceForecaster):
    """Expected absent people per day with an 80 % conformal interval; department level only."""

    def __init__(self, bundle_dir: Path | None = None) -> None:
        """Load the champion bundle (``C3_BUNDLE_DIR`` or the committed one)."""
        path = bundle_dir or Path(os.environ.get("C3_BUNDLE_DIR", BUNDLE_DIR))
        self.bundle = load_bundle(path)
        self.info = _info(self.bundle, bundle_sha256(path))

    def forecast(
        self, days: list[date], history: list[tuple[date, date]], context: ForecastContext
    ) -> list[AbsenceForecast]:
        """Forecast the days; the origin is the day before ``context.as_of``."""
        origin = context.as_of - timedelta(days=1)
        horizons = [(d - origin).days for d in days]
        if any(h not in HORIZONS for h in horizons):
            raise ValueError("C3 forecasts 1 to 42 days ahead of the day before 'as of'")
        builder = FeatureBuilder(
            daily_counts(history, SERIES_START, origin),
            Calendar(context.holidays, context.school_holidays),
            context.night_shifts,
        )
        mu, low, high = self.bundle.forecast(builder, origin, horizons)
        return [
            AbsenceForecast(d, round(float(m), 2), round(float(lo), 2), round(float(hi), 2))
            for d, m, lo, hi in zip(days, mu, low, high, strict=True)
        ]
