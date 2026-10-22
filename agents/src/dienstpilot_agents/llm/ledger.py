"""The append-only usage ledger: one JSON line per paid call, committed to the repository.

It is the budget's source of truth. It lives in a file, not in the database, because ``make seed``
and ``--reset`` drop the database schemas and a budget that forgets what was spent is no budget.
It holds token counts and cost only, never prompt or response text.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PATH = Path(__file__).resolve().parents[4] / "eval" / "usage" / "ledger.jsonl"


@dataclass(frozen=True)
class Entry:
    """One paid call."""

    seq: int
    run_id: str
    component: str
    purpose: str  # dev | test | latency | record | app
    model: str
    mode: str  # live | batch
    request: str  # first 12 characters of the request key
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    cost_usd: float
    cumulative_usd: float


class Ledger:
    """Reads and appends the ledger file."""

    def __init__(self, path: Path | None = None) -> None:
        """Use ``path`` (default: ``eval/usage/ledger.jsonl``, or ``LLM_LEDGER``)."""
        self.path = path or Path(os.environ.get("LLM_LEDGER", PATH))

    def entries(self) -> list[Entry]:
        """Return every entry in order."""
        if not self.path.exists():
            return []
        return [
            Entry(**json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def total_usd(self) -> float:
        """Return everything spent so far."""
        entries = self.entries()
        return entries[-1].cumulative_usd if entries else 0.0

    def append(self, **fields: Any) -> Entry:
        """Add one entry (``seq`` and ``cumulative_usd`` are set here)."""
        prior = self.entries()
        seq = prior[-1].seq + 1 if prior else 1
        cumulative = round((prior[-1].cumulative_usd if prior else 0.0) + fields["cost_usd"], 6)
        entry = Entry(seq=seq, cumulative_usd=cumulative, **fields)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.__dict__, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return entry
