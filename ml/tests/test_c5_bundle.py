"""The committed C5 bundle holds model parameters only (privacy rule)."""

import json
import re
from pathlib import Path

import polars as pl
import pytest

from dienstpilot_ml.cover_ranker.models import bundle_sha256, load_bundle

ROOT = Path(__file__).resolve().parents[1] / "cover_ranker" / "artifacts"
DATA = Path(__file__).resolve().parents[2] / "data/synthetic/v1"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
ALLOWED_KEYS = {
    "format", "kind", "features", "shift_types", "meta", "rate", "mean", "std", "coef",
    "intercept", "calibrator",
}  # fmt: skip


def _files() -> list[Path]:
    return [p for p in ROOT.rglob("*") if p.is_file()]


def test_the_bundle_has_only_model_keys_and_loads() -> None:
    doc = json.loads((ROOT / "champion" / "bundle.json").read_text())
    assert set(doc) <= ALLOWED_KEYS
    assert all(isinstance(v, str) for v in doc["meta"].values())
    b = load_bundle(ROOT / "champion")
    assert b.kind == doc["kind"]
    assert len(bundle_sha256(ROOT / "champion")) == 64


def test_no_staff_identifier_appears_in_any_committed_artifact() -> None:
    for f in _files():
        assert not UUID.search(f.read_text()), f"{f.name} contains an identifier-like value"


@pytest.mark.skipif(not DATA.exists(), reason="needs the generated dataset")
def test_no_staff_id_of_the_dataset_appears_in_any_committed_artifact() -> None:
    ids = pl.read_parquet(DATA / "organization/staff.parquet")["id"].to_list()
    assert ids
    text = "".join(f.read_text() for f in _files())
    assert not any(i in text for i in ids)
