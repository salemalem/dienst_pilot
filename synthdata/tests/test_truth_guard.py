"""Nothing outside synthdata/ and eval/ may refer to the _truth/ folder (ARCHITECTURE §8.1)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUARDED = ["backend", "ml", "engine", "agents", "mcp_servers", "apps", "packages"]
SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".toml", ".yaml", ".yml", ".ipynb", ".sql"}
SKIP = {"node_modules", ".next", ".expo", "dist", "__pycache__", ".venv"}


def test_no_code_outside_synthdata_and_eval_reads_truth() -> None:
    offenders = []
    for top in GUARDED:
        for path in (REPO / top).rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES or SKIP & set(path.parts):
                continue
            if "_truth" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(REPO)))
    assert offenders == []
