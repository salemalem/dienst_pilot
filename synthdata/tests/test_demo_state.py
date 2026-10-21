"""The demo state matches UI_SPEC §1 and the November 2026 roster passes every hard rule."""

import json
from datetime import date, datetime
from pathlib import Path

import polars as pl

from hard_rules import Dataset, check_all, check_month
from synthdata.config import DEMO_NOW
from tests_support import read

NOVEMBER = date(2026, 11, 1)
UI_SPEC_NAMES = {
    "Prof. Dr. Claudia Hoffmann",
    "Dr. Thomas Brandt",
    "Dr. Lea Lorenz",
    "Dr. Aylin Kaya",
    "Dr. Rohan Mehta",
    "Dr. Jonas Weber",
    "Dr. Sofía Alvarez",
    "Dr. Marek Nowak",
    "Dr. Hannah Schulz",
    "Dr. Yusuf Demir",
    "Dr. Ines Becker",
    "Dr. Felix Wagner",
    "Dr. Mira Okafor",
    "Dr. Paul Richter",
    "Dr. Anna Lehmann",
    "Dr. Tobias Klein",
    "Dr. Elif Arslan",
}


def _published_at(dataset: Path, month: date) -> datetime:
    run = read(dataset, "planning/roster_run").filter(pl.col("roster_month") == month)
    v = read(dataset, "planning/roster_variant").filter(pl.col("run_id") == run["id"][0])
    published: datetime = v["published_at"][0]
    return published


def test_november_2026_roster_passes_every_hard_rule(dataset: Path) -> None:
    problems = check_month(Dataset(dataset), NOVEMBER)
    assert problems == []


def test_november_2026_is_published_by_dr_brandt_on_19_october(dataset: Path) -> None:
    run = read(dataset, "planning/roster_run").filter(pl.col("roster_month") == NOVEMBER)
    assert run["rule_set_version"].to_list() == ["2026-1"]
    published = _published_at(dataset, NOVEMBER).astimezone(DEMO_NOW.tzinfo)
    assert published.date() == date(2026, 10, 19)
    approval = read(dataset, "planning/approval")
    staff = read(dataset, "organization/staff")
    approver = approval.join(staff, left_on="approved_by", right_on="id")
    assert set(approver["display_name"]) == {"Dr. Thomas Brandt"}


def test_no_roster_after_november_2026(dataset: Path) -> None:
    months = read(dataset, "planning/roster_run")["roster_month"]
    assert months.max() == NOVEMBER
    assert months.min() == date(2021, 1, 1)


def test_team_on_demo_date_is_28_with_the_ui_spec_names(dataset: Path) -> None:
    c = read(dataset, "organization/contract").filter(
        (pl.col("valid_from") <= date(2026, 10, 20))
        & (pl.col("valid_to").is_null() | (pl.col("valid_to") >= date(2026, 10, 20)))
    )
    assert c.height == 28
    assert dict(c.group_by("role").len().iter_rows()) == {
        "chefaerztin": 1,
        "oberarzt": 4,
        "facharzt": 7,
        "assistenzarzt": 16,
    }
    names = set(
        read(dataset, "organization/staff").filter(pl.col("id").is_in(c["staff_id"].implode()))[
            "display_name"
        ]
    )
    assert names >= UI_SPEC_NAMES


def test_december_window_is_open_with_21_of_28_and_without_dr_kaya(dataset: Path) -> None:
    w = read(dataset, "requests/request_window").filter(pl.col("roster_month") == date(2026, 12, 1))
    assert w["status"].to_list() == ["open"]
    assert w["recipient_count"].to_list() == [28]
    tz = DEMO_NOW.tzinfo
    assert w["opens_at"][0].astimezone(tz).date() == date(2026, 10, 12)
    assert w["closes_at"][0].astimezone(tz) == datetime(2026, 10, 26, 23, 59, tzinfo=tz)
    resp = read(dataset, "requests/window_response").filter(pl.col("window_id") == w["id"][0])
    assert resp.height == 21
    kaya = read(dataset, "organization/staff").filter(pl.col("display_name") == "Dr. Aylin Kaya")[
        "id"
    ][0]
    assert kaya not in resp["staff_id"].to_list()


def test_every_other_window_is_closed(dataset: Path) -> None:
    w = read(dataset, "requests/request_window")
    assert w.filter(pl.col("status") == "open")["roster_month"].to_list() == [date(2026, 12, 1)]


def test_nothing_happens_after_the_demo_moment(dataset: Path) -> None:
    for name in (
        "operations/absence",
        "operations/swap_offer",
        "operations/cover_cascade",
        "operations/cover_offer",
        "requests/leave_request",
        "requests/window_response",
        "planning/roster_variant",
        "planning/approval",
    ):
        df = read(dataset, name)
        for col, dtype in df.schema.items():
            if isinstance(dtype, pl.Datetime):
                latest = df[col].drop_nulls().max()
                assert latest is None or latest <= DEMO_NOW, f"{name}.{col}"


def test_rule_versioning(dataset: Path) -> None:
    rs = read(dataset, "organization/rule_set").sort("effective_from")
    assert rs["version"].to_list() == ["2021-1", "2026-1"]
    v1, v2 = (json.loads(r) for r in rs["rules"])
    assert (v1["max_weekends_per_month"], v1["max_on_call_per_month"]) == (2, 4)
    assert (v1["max_consecutive_nights"], v2["max_consecutive_nights"]) == (4, 3)
    assert {k for k in v1 if v1[k] != v2[k]} == {"max_consecutive_nights"}
    assert v1["contract_hours_band"] == [0.8, 1.1] and v1["contract_hours_band_min_days"] == 5


def test_published_rosters_break_only_coverage(dataset: Path) -> None:
    v = read(dataset, "_truth/published_violations")
    assert set(v["rule"].to_list()) <= {"coverage"}
    assert v.filter(pl.col("roster_month") == NOVEMBER).is_empty()


def test_every_published_month_breaks_only_coverage_and_matches_the_record(dataset: Path) -> None:
    problems = check_all(dataset)
    assert len(problems) == 71  # January 2021 to November 2026
    other = [p for ps in problems.values() for p in ps if p.rule != "coverage"]
    assert other == []
    found = {(p.day, p.detail) for ps in problems.values() for p in ps}
    truth = read(dataset, "_truth/published_violations")
    recorded = {(r["date"], r["detail"].split(":")[0]) for r in truth.iter_rows(named=True)}
    assert found == recorded
