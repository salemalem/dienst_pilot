"""Reproducibility, schema and privacy properties of the generated dataset."""

import json
from datetime import time
from pathlib import Path

import polars as pl

from synthdata.cli import main
from synthdata.config import DEFAULT_SEED
from tests_support import read


def test_same_seed_gives_identical_output(dataset: Path, tmp_path: Path) -> None:
    again = tmp_path / "v1"
    assert main(["generate", "--seed", str(DEFAULT_SEED), "--out", str(again)]) == 0
    first = json.loads((dataset / "manifest.json").read_text())
    second = json.loads((again / "manifest.json").read_text())
    assert first == second
    for rel in [*first["files"], *first["truth_files"], "_truth/params.json"]:
        assert (dataset / rel).read_bytes() == (again / rel).read_bytes(), rel


def test_a_different_seed_gives_different_output(dataset: Path, tmp_path: Path) -> None:
    other = tmp_path / "v1"
    assert main(["generate", "--seed", str(DEFAULT_SEED + 1), "--out", str(other)]) == 0
    a = json.loads((dataset / "manifest.json").read_text())["files"]
    b = json.loads((other / "manifest.json").read_text())["files"]
    assert a["planning/assignment.parquet"]["sha256"] != b["planning/assignment.parquet"]["sha256"]


def test_manifest_counts_and_demo_period(dataset: Path) -> None:
    m = json.loads((dataset / "manifest.json").read_text())
    assert m["seed"] == DEFAULT_SEED
    assert m["periods"]["history"] == {
        "start": "2021-01-01",
        "end": "2025-12-31",
        "use": "training and evaluation",
    }
    assert m["periods"]["demo"]["start"] == "2026-01-01"
    assert "demo period" in m["periods"]["demo"]["use"]
    for rel, info in m["files"].items():
        assert pl.read_parquet(dataset / rel).height == info["rows"], rel
    assert all(rel.startswith("_truth/") for rel in m["truth_files"])


def test_shift_types_match_ui_spec(dataset: Path) -> None:
    st = {r["code"]: r for r in read(dataset, "organization/shift_type").iter_rows(named=True)}
    expected = {
        "frueh": ("F", "E", time(7, 30), time(16, 0), False, 30, 8.0),
        "spaet": ("S", "L", time(13, 30), time(22, 0), False, 30, 8.0),
        "nacht": ("N", "N", time(21, 30), time(8, 0), True, 45, 9.75),
        "bereitschaft": ("B", "O", time(8, 0), time(8, 0), True, 0, 24.0),
        "ruf": ("R", "H", time(16, 0), time(7, 30), True, 0, 0.0),
        "frei": ("U", "V", None, None, False, 0, 8.0),
    }
    got = {
        k: (
            r["letter_de"],
            r["letter_en"],
            r["start_time"],
            r["end_time"],
            r["ends_next_day"],
            r["break_minutes"],
            r["net_hours"],
        )
        for k, r in st.items()
    }
    assert got == expected


def test_sickness_holds_only_status_and_dates(dataset: Path) -> None:
    ab = read(dataset, "operations/absence")
    assert ab.columns == ["id", "staff_id", "start_date", "end_date", "category", "reported_at"]
    assert set(ab["category"].to_list()) == {"sick"}


def test_leave_stores_only_the_planners_reason_for_declines(dataset: Path) -> None:
    lr = read(dataset, "requests/leave_request")
    assert "reason" not in lr.columns and "requester_reason" not in lr.columns
    assert lr.filter(
        (pl.col("status") != "declined") & pl.col("decision_reason").is_not_null()
    ).is_empty()
    assert lr.filter(
        (pl.col("status") == "declined") & pl.col("decision_reason").is_null()
    ).is_empty()


def test_no_protected_attributes(dataset: Path) -> None:
    forbidden = {
        "gender",
        "sex",
        "age",
        "birth_date",
        "nationality",
        "religion",
        "family_status",
        "children",
    }
    for rel in json.loads((dataset / "manifest.json").read_text())["files"]:
        assert not forbidden & set(pl.read_parquet(dataset / rel).columns), rel


def test_staff_structure_is_stable(dataset: Path) -> None:
    c = read(dataset, "organization/contract")
    for year in range(2021, 2027):
        for month in (1, 7):
            d = pl.date(year, month, 15)
            active = c.filter(
                (pl.col("valid_from") <= d)
                & (pl.col("valid_to").is_null() | (pl.col("valid_to") >= d))
            )
            assert active.height == 28, (year, month)


def test_seasonal_absence_wave(dataset: Path) -> None:
    ab = read(dataset, "operations/absence")
    winter = ab.filter(pl.col("start_date").dt.month().is_in([12, 1, 2])).height / 3
    summer = ab.filter(pl.col("start_date").dt.month().is_in([6, 7, 8])).height / 3
    assert winter > 1.5 * summer


def test_operations_refer_to_published_assignments(dataset: Path) -> None:
    ids = set(read(dataset, "planning/assignment")["id"].to_list())
    for name in ("operations/swap_offer", "operations/cover_cascade"):
        refs = set(read(dataset, name)["assignment_id"].to_list())
        assert refs <= ids, name
    staff = set(read(dataset, "organization/staff")["id"].to_list())
    for name, col in [
        ("planning/assignment", "staff_id"),
        ("operations/absence", "staff_id"),
        ("requests/preference", "staff_id"),
        ("operations/cover_offer", "staff_id"),
    ]:
        assert set(read(dataset, name)[col].to_list()) <= staff, name
