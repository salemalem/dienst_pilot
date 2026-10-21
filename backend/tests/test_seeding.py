import hashlib
import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from sqlalchemy import create_engine, text

from dienstpilot.seeding import (
    ResetRefusedError,
    SeedError,
    check_reset_target,
    load,
    reset,
    verify,
)
from dienstpilot.shared.settings import get_settings

REPO = Path(__file__).resolve().parents[2]


def _copy(seed_dir: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "v1"
    shutil.copytree(seed_dir, dst)
    return dst


def test_verify_accepts_the_generated_seed(seed_dir: Path) -> None:
    manifest = verify(seed_dir)
    assert manifest["generator_version"]


def test_verify_rejects_a_changed_file(seed_dir: Path, tmp_path: Path) -> None:
    root = _copy(seed_dir, tmp_path)
    path = root / "planning" / "assignment.parquet"
    df = pl.read_parquet(path)
    df.head(df.height - 1).write_parquet(path)
    with pytest.raises(SeedError, match="does not match the manifest"):
        verify(root)


def test_verify_rejects_a_dangling_cross_context_reference(seed_dir: Path, tmp_path: Path) -> None:
    root = _copy(seed_dir, tmp_path)
    path = root / "planning" / "assignment.parquet"
    df = pl.read_parquet(path)
    df = df.with_columns(pl.lit("00000000-0000-0000-0000-000000000000").alias("staff_id"))
    df.write_parquet(path)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["files"]["planning/assignment.parquet"]["sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SeedError, match=r"planning/assignment\.staff_id"):
        verify(root)


@pytest.mark.db
def test_seed_loads_every_table_and_is_repeatable(seed_dir: Path, database_url: str) -> None:
    manifest = json.loads((seed_dir / "manifest.json").read_text())
    first = load(seed_dir, database_url)
    second = load(seed_dir, database_url)
    expected = {
        rel.removesuffix(".parquet"): info["rows"] for rel, info in manifest["files"].items()
    }
    assert first == second
    assert {k: v for k, v in first.items() if k in expected} == expected
    assert first["identity/user"] == 11  # the demo personas
    assert first["audit/event"] > 1000  # the history backfilled into the audit trail


@pytest.mark.db
def test_seeded_database_holds_the_demo_state(seed_dir: Path, database_url: str) -> None:
    load(seed_dir, database_url)
    engine = create_engine(database_url)
    with engine.connect() as conn:
        window = conn.execute(
            text(
                "SELECT status, recipient_count FROM requests.request_window"
                " WHERE roster_month = :m"
            ),
            {"m": date(2026, 12, 1)},
        ).one()
        responses = conn.execute(
            text(
                "SELECT count(*) FROM requests.window_response r JOIN requests.request_window w"
                " ON w.id = r.window_id WHERE w.roster_month = :m"
            ),
            {"m": date(2026, 12, 1)},
        ).scalar_one()
        november = conn.execute(
            text("SELECT rule_set_version FROM planning.roster_run WHERE roster_month = :m"),
            {"m": date(2026, 11, 1)},
        ).scalar_one()
        rules = (
            conn.execute(
                text(
                    "SELECT rules->>'max_consecutive_nights' FROM organization.rule_set"
                    " ORDER BY effective_from"
                )
            )
            .scalars()
            .all()
        )
    engine.dispose()
    assert (window.status, window.recipient_count, responses) == ("open", 28, 21)
    assert november == "2026-1"
    assert rules == ["4", "3"]


@pytest.mark.db
def test_models_match_the_migrations(database_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        ["alembic", "check"], cwd=REPO / "backend", env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("url", "demo_mode", "ci", "why"),
    [
        ("postgresql+psycopg://u:p@localhost:5433/prod", True, False, "not a DienstPilot"),
        ("postgresql+psycopg://u:p@localhost:5433/postgres", True, False, "not a DienstPilot"),
        ("postgresql+psycopg://u:p@localhost:5432/dienstpilot", True, False, "only port 5433"),
        ("postgresql+psycopg://u:p@db.example.com:5433/dienstpilot", True, False, "not a local"),
        ("postgresql+psycopg://u:p@localhost:5433/dienstpilot", False, False, "DEMO_MODE"),
        ("postgresql+psycopg://u:p@localhost:6543/dienstpilot_e2e", True, True, "only port 5433"),
    ],
)
def test_reset_refuses_a_database_that_is_not_the_dev_or_e2e_one(
    url: str, demo_mode: bool, ci: bool, why: str
) -> None:
    with pytest.raises(ResetRefusedError, match=why):
        check_reset_target(url, demo_mode=demo_mode, ci=ci)


def test_reset_accepts_the_dev_and_e2e_databases_and_names_them() -> None:
    dev = "postgresql+psycopg://u:p@localhost:5433/dienstpilot"
    e2e = "postgresql+psycopg://u:p@127.0.0.1:5433/dienstpilot_e2e"
    ci = "postgresql+psycopg://u:p@localhost:5432/dienstpilot"
    assert check_reset_target(dev, demo_mode=True) == "dienstpilot on localhost:5433"
    assert "dienstpilot_e2e" in check_reset_target(e2e, demo_mode=True)
    assert check_reset_target(ci, demo_mode=True, ci=True) == "dienstpilot on localhost:5432"


@pytest.mark.db
def test_reset_rebuilds_a_database_the_app_has_written_to(
    seed_dir: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the app wrote rows (an approved swap), `make seed` must still rebuild from nothing."""
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    try:
        expected = verify(seed_dir)["files"]["operations/swap_offer.parquet"]["rows"]
        load(seed_dir, database_url)
        engine = create_engine(database_url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE operations.swap_offer SET status = 'approved' "
                    "WHERE id = (SELECT id FROM operations.swap_offer LIMIT 1)"
                )
            )
        engine.dispose()
        reset(database_url, ci=os.environ.get("CI") == "true")
        env = {**os.environ, "DATABASE_URL": database_url}
        subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=REPO / "backend", env=env)
        load(seed_dir, database_url)
        engine = create_engine(database_url)
        with engine.connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM operations.swap_offer")).scalar_one()
            approved = conn.execute(
                text("SELECT count(*) FROM operations.swap_offer WHERE status = 'approved'")
            ).scalar_one()
        engine.dispose()
        assert n == expected
        assert approved == 0
    finally:
        get_settings.cache_clear()
