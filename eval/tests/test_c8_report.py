"""C8: the committed results are the ones the recorded runs give, and the privacy scan is clean.

No model, no database, no network: the report is recomputed from the committed records with the
current scoring and grounding code. The privacy scan re-reads every text that was sent to the
model in every recorded run against the synthetic staff list.
"""

import json
import sys
from pathlib import Path

import polars as pl
import pytest

from dienstpilot_agents.copilot.guard import Aliases

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "eval"))
import run_c8_eval as r  # noqa: E402

PERSONAS = (
    "kaya",
    "mehta",
    "weber",
    "alvarez",
    "nowak",
    "lorenz",
    "schulz",
    "brandt",
    "hoffmann",
    "vogel",
)


def test_the_committed_report_is_what_the_recorded_runs_give() -> None:
    r.report(check=True)


def test_the_frozen_prompt_is_the_one_in_the_code_and_the_files_did_not_change() -> None:
    f = json.loads(r.FROZEN.read_text())
    suite = r.load()
    assert f["prompt_sha256"] == r.prompt_sha()
    assert f["tasks_sha256"] == suite["sha256_tasks"] and f["split_sha256"] == suite["sha256_split"]
    assert f["gates_sha256"] == r._sha(r.GATES)


def test_every_test_run_used_the_frozen_prompt_and_each_task_ran_once() -> None:
    f = json.loads(r.FROZEN.read_text())
    suite = r.load()
    test = r.records("test")
    assert sorted(test) == sorted(suite["split"]["test"])
    for rec in test.values():
        assert (
            rec["prompt_version"] == f["prompt_version"]
            and rec["meta"]["prompt_sha"] == f["prompt_sha256"]
        )


def test_no_text_sent_to_the_model_in_any_recorded_run_holds_a_name_an_id_or_a_health_word(
    seed_root: Path,
) -> None:
    staff = {
        str(row["id"]): row["display_name"]
        for row in pl.read_parquet(seed_root / "organization" / "staff.parquet").iter_rows(
            named=True
        )
    }
    a = Aliases(staff)
    scanned = 0
    for label in sorted(p.name for p in r.RUNS.iterdir() if p.is_dir()):
        for tid, rec in r.records(label).items():
            for turn in rec["turns"]:
                found = a.findings(turn["new_text"], PERSONAS, health=False)
                assert not found, (label, tid, found)
                scanned += 1
    assert scanned > 100


def test_a_failed_or_privacy_stopped_run_never_has_a_model_answer_shown() -> None:
    for rec in r.records("test").values():
        if rec["aborted"]:
            assert rec["fallback"] and (
                "nicht gegen die Daten" in rec["served"] or "could not be checked" in rec["served"]
            )


@pytest.mark.parametrize("label", ["dev-1", "dev-2", "dev-3", "latency", "test"])
def test_records_exist_for_each_run(label: str) -> None:
    assert r.records(label)
