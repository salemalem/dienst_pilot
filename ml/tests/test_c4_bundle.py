"""The committed C4 bundle holds department-level numbers only (privacy rule)."""

import json
import re
from pathlib import Path

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1] / "preference_learner" / "artifacts"
DATA = Path(__file__).resolve().parents[2] / "data/synthetic/v1"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
ALLOWED_KEYS = {
    "format", "kind", "shifts", "cells", "m_wish", "m_avoid", "kappa_wish", "kappa_avoid",
    "p_clip", "meta",
}  # fmt: skip


def _files() -> list[Path]:
    return [p for p in ROOT.rglob("*") if p.is_file()]


def test_the_bundle_has_only_department_level_keys_and_fixed_length_arrays() -> None:
    doc = json.loads((ROOT / "champion" / "bundle.json").read_text())
    assert set(doc) == ALLOWED_KEYS
    assert len(doc["m_wish"]) == len(doc["m_avoid"]) == 28  # one rate per cell, no person axis
    assert all(isinstance(x, float) for x in doc["m_wish"] + doc["m_avoid"])
    assert all(isinstance(v, str) for v in doc["meta"].values())


def test_no_staff_identifier_appears_in_any_committed_artifact() -> None:
    for f in _files():
        assert not UUID.search(f.read_text()), f"{f.name} contains an identifier-like value"


@pytest.mark.skipif(not DATA.exists(), reason="needs the generated dataset")
def test_no_staff_id_of_the_dataset_appears_in_any_committed_artifact() -> None:
    ids = pl.read_parquet(DATA / "organization/staff.parquet")["id"].to_list()
    assert ids
    text = "".join(f.read_text() for f in _files())
    assert not any(i in text for i in ids)
