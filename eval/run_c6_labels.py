"""Generate the C6 leave-feasibility labels (solver runs; slow, resumable, deterministic).

Usage:
  uv run python eval/run_c6_labels.py --split train --pilot 150   # the first 150 of a fixed order
  uv run python eval/run_c6_labels.py --split train               # all of 2021-2024, resumes
  uv run python eval/run_c6_labels.py --split test                # 2025
  uv run python eval/run_c6_labels.py --fidelity 200              # re-solve 200 with workers=8
  uv run python eval/run_c6_labels.py --sample                    # the small CI sample

Labels go to ml/leave_surrogate/labels/<split>.jsonl, one JSON object per request, sorted by id
when a run finishes (so the file is byte-identical for a given dataset and solver). A label is
the M5 decision (``dienstpilot_solver.coverability``) with the protocol of
ml/leave_surrogate/PROMOTION_RULE.md. ``make labels`` runs it under ``caffeinate`` on macOS.
"""

import argparse
import hashlib
import json
import multiprocessing as mp
import random
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data" / "synthetic" / "v1"
OUT = REPO / "ml" / "leave_surrogate" / "labels"

_world: Any = None
_cfg: Any = None


def _init(workers: int) -> None:
    global _world, _cfg
    from dienstpilot_eval.c6_labels import CHECK_CONFIG, World

    _world = World(ROOT)
    _cfg = replace(CHECK_CONFIG, workers=workers)


def _one(spec: Any) -> dict[str, Any]:
    from dienstpilot_eval.c6_labels import label

    return label(_world, spec, _cfg).to_json()


def _read(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {j["id"]: j for j in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def _write_sorted(path: Path, rows: dict[str, dict[str, Any]]) -> None:
    lines = [json.dumps(rows[k], sort_keys=True) for k in sorted(rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _summary(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    out: dict[str, Any] = {"n": n, "outcomes": {}, "by_stratum": {}}
    for r in rows.values():
        out["outcomes"][r["outcome"]] = out["outcomes"].get(r["outcome"], 0) + 1
        s = out["by_stratum"].setdefault(r["stratum"], {})
        s[r["outcome"]] = s.get(r["outcome"], 0) + 1
    if n:
        out["mean_solves"] = round(sum(r["solves"] for r in rows.values()) / n, 2)
        out["mean_solve_seconds"] = round(sum(r["solve_seconds"] for r in rows.values()) / n, 2)
    return out


def generate(split: str, procs: int, workers: int, pilot: int | None, per_month: int | None) -> None:
    """Fill ``labels/<split>.jsonl`` (all requests, or the pilot head); resumable."""
    from dienstpilot_eval.c6_labels import pilot_order, specs

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{split}.jsonl"
    rows = _read(path)
    todo = pilot_order(specs(split, per_month))
    if pilot:
        todo = todo[:pilot]
    todo = [s for s in todo if s.id not in rows]
    print(f"{split}: {len(rows)} done, {len(todo)} to do, {procs} processes x {workers} workers", flush=True)
    t0 = time.perf_counter()
    with mp.get_context("spawn").Pool(procs, _init, (workers,)) as pool, path.open("a", encoding="utf-8") as f:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1), 1):
            rows[r["id"]] = r
            f.write(json.dumps(r, sort_keys=True) + "\n")
            f.flush()
            if i % 25 == 0 or i == len(todo):
                dt = time.perf_counter() - t0
                print(f"  {i}/{len(todo)}  {dt:.0f}s  eta {dt / i * (len(todo) - i):.0f}s", flush=True)
    _write_sorted(path, rows)
    print(json.dumps(_summary(rows), indent=1))


def fidelity(n: int) -> None:
    """Re-solve n random labels with the product's exact CHECK_CONFIG and count differences."""
    from dienstpilot_eval.c6_labels import CHECK_CONFIG, Spec, World, label

    from datetime import date

    rows = {**_read(OUT / "train.jsonl"), **_read(OUT / "test.jsonl")}
    pick = random.Random("c6-fidelity").sample(sorted(rows), n)
    w = World(ROOT)
    differ = []
    for i, k in enumerate(pick, 1):
        split, month, idx = k.split("|")
        got = label(w, Spec(split, date.fromisoformat(month), int(idx)), CHECK_CONFIG)
        if got.outcome != rows[k]["outcome"]:
            differ.append({"id": k, "stored": rows[k]["outcome"], "exact": got.outcome})
        print(f"  {i}/{n} differ so far {len(differ)}", flush=True)
    doc = {"config": "CHECK_CONFIG (workers=8) against labels solved with workers=2",
           "n": n, "differ": len(differ), "share": len(differ) / n, "details": differ}
    (OUT / "fidelity.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(doc, indent=1))


def sample(n: int = 40) -> None:
    """Write the small committed CI sample: an even draw of train labels over strata."""
    rows = _read(OUT / "train.jsonl")
    rnd = random.Random("c6-sample")
    by: dict[str, list[str]] = {}
    for k, r in rows.items():
        by.setdefault(f"{r['stratum']}|{r['outcome']}", []).append(k)
    pick: list[str] = []
    groups = sorted(by)
    while len(pick) < n and any(by.values()):
        for g in groups:
            if by[g] and len(pick) < n:
                pick.append(by[g].pop(rnd.randrange(len(by[g]))))
    _write_sorted(OUT / "sample.jsonl", {k: rows[k] for k in pick})


def seal() -> None:
    """Write meta.json: versions, dataset hash and file hashes of the finished labels."""
    from dienstpilot_eval.c6_labels import SEED, VERSIONS

    manifest = hashlib.sha256((ROOT / "manifest.json").read_bytes()).hexdigest()
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob("*.jsonl"))}
    meta = {"seed": SEED, "versions": VERSIONS, "dataset_manifest_sha256": manifest, "files": files,
            "summary": {s: _summary(_read(OUT / f"{s}.jsonl")) for s in ("train", "test")}}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["train", "test"])
    ap.add_argument("--pilot", type=int)
    ap.add_argument("--per-month", type=int)
    ap.add_argument("--procs", type=int, default=5)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--fidelity", type=int)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--seal", action="store_true")
    a = ap.parse_args()
    if a.fidelity:
        fidelity(a.fidelity)
    elif a.sample:
        sample()
    elif a.seal:
        seal()
    else:
        assert a.split, "--split is required"
        generate(a.split, a.procs, a.workers, a.pilot, a.per_month)
