"""The C5 adapter: bundle identity, the ordering policy, and no probability in the output."""

import json
from dataclasses import fields

import numpy as np

from dienstpilot.engines.c5 import BUNDLE_DIR, RESULT, C5CoverRanker
from dienstpilot.shared.ports import CoverCandidate
from dienstpilot_ml.cover_ranker.models import Bundle, bundle_sha256


def _cand(staff: str, covers: int, hours: float, **kw: float) -> CoverCandidate:
    return CoverCandidate(staff, covers, hours, **kw)  # type: ignore[arg-type]


def test_the_committed_bundle_is_the_one_the_eval_result_describes() -> None:
    doc = json.loads(RESULT.read_text(encoding="utf-8"))
    assert bundle_sha256(BUNDLE_DIR) == doc["champion"]["bundle_sha256"]
    info = C5CoverRanker().info
    assert info.implementation == "built" and info.component == "C5"
    assert doc["champion"]["kind"].replace("_", "") in info.version.replace("_", "")


def test_the_port_output_carries_no_probability() -> None:
    assert not [f.name for f in fields(CoverCandidate) if "p_" in f.name or "prob" in f.name]
    ranked = C5CoverRanker().rank([_cand("a", 0, 0.5), _cand("b", 1, 0.7)])
    assert all(isinstance(c, CoverCandidate) for c in ranked)


def test_a_strong_probability_never_beats_a_lower_burden_bucket() -> None:
    # A logistic model that loves a long time since the last cover (a heavy-signal stand-in).
    from dienstpilot_ml.features.cover import NUMERIC, SHIFT_TYPES

    coef = np.zeros(len(NUMERIC) + len(SHIFT_TYPES))
    coef[NUMERIC.index("days_since_last_cover")] = 5.0
    ranker = C5CoverRanker()
    ranker.bundle = Bundle("logistic", {"c5_version": "test"}, coef=coef)
    rested = _cand("rested", 3, 0.5, days_since_last_cover=365.0)  # bucket 1, P high
    busy = _cand("busy", 1, 0.9, days_since_last_cover=0.5)  # bucket 0, P low
    peer = _cand("peer", 0, 0.9, days_since_last_cover=300.0)  # bucket 0, P higher than busy
    assert [c.staff_id for c in ranker.rank([rested, busy, peer])] == ["peer", "busy", "rested"]


def test_without_a_signal_the_order_inside_a_bucket_follows_hours_against_contract() -> None:
    ranker = C5CoverRanker()
    ranker.bundle = Bundle("base_rate", {"c5_version": "test"}, rate=0.5)
    cands = [_cand("a", 1, 0.9), _cand("b", 0, 0.6), _cand("c", 2, 0.1)]
    assert [c.staff_id for c in ranker.rank(cands)] == ["b", "a", "c"]
    assert ranker.rank([]) == []
