"""The README's results block is rendered from eval/results/*.json and must be current."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "eval"))
import render_readme  # noqa: E402


def test_readme_results_block_matches_the_result_files() -> None:
    assert render_readme.main(["--check"]) == 0


def test_the_prose_around_the_block_states_no_result_figure() -> None:
    text = render_readme.README.read_text(encoding="utf-8")
    start, end = text.index(render_readme.START), text.index(render_readme.END)
    prose = text[:start] + text[end:]
    for figure in ("62.8", "39.6", "99.3", "71/71", "300/300", "492", "55.45"):
        assert figure not in prose, f"{figure} is a result and belongs in the generated block"
