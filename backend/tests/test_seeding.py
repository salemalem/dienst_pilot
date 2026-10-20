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

from dienstpilot.seeding import SeedError, load, verify

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
    assert first == second == expected


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
