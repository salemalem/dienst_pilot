"""Evaluate retrieval over the rulebook: recall@k, MRR, citation correctness, "no source".

Usage:
  uv run python eval/run_rag_eval.py [--database-url URL]   # -> eval/results/rag.json

Follows agents/rag/EVAL_RULE.md (committed before the first run): the "no source" threshold is
chosen on the dev questions only and written to agents/rag/threshold.json; the test questions are
then scored with it. Needs a Postgres with migration 0011 (the index is rebuilt there from the
committed vectors) and no embedding model: question vectors are the committed ones.
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from dienstpilot_agents.rag import vectors
from dienstpilot_agents.rag.corpus import corpus_hash, load_corpus
from dienstpilot_agents.rag.search import RRF_K, TOP_K, search
from dienstpilot_agents.rag.store import load_index
from sqlalchemy import create_engine

REPO = Path(__file__).resolve().parents[1]
RULE = REPO / "agents" / "rag" / "EVAL_RULE.md"
QUESTIONS = REPO / "eval" / "rag_questions.json"
THRESHOLD = REPO / "agents" / "rag" / "threshold.json"
OUT = REPO / "eval" / "results" / "rag.json"
GRID = [round(0.30 + 0.025 * i, 3) for i in range(17)]
DEV_BELOW = 86


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def is_dev(question_id: str) -> bool:
    """Dev if the first byte of the SHA-256 of the id is below 86 (EVAL_RULE.md)."""
    return int(hashlib.sha256(question_id.encode()).hexdigest()[:2], 16) < DEV_BELOW


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO, check=False)
    return out.stdout.strip()


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ans = [r for r in rows if r["answerable"]]

    def recall(k: int) -> float:
        return sum(any(i in r["gold"] for i in r["ranked"][:k]) for r in ans) / len(ans)

    def mrr() -> float:
        total = 0.0
        for r in ans:
            for pos, i in enumerate(r["ranked"], start=1):
                if i in r["gold"]:
                    total += 1 / pos
                    break
        return total / len(ans)

    return {
        "n_answerable": len(ans),
        "recall@1": round(recall(1), 4),
        "recall@3": round(recall(3), 4),
        "recall@5": round(recall(5), 4),
        "mrr": round(mrr(), 4),
        "citation_correct@1": round(recall(1), 4),
    }


def main() -> None:
    """Run the evaluation and write eval/results/rag.json."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url")
    args = ap.parse_args()
    url = args.database_url or os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("give --database-url (a Postgres with migration 0011)")
    _, chunks = load_corpus()
    cv = vectors.load("chunks", [c.embed_text for c in chunks])
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    qv = vectors.load("questions", [q["question"] for q in qs])
    emb = qv.embedder()
    engine = create_engine(url)
    runs: dict[str, list[dict[str, Any]]] = {"hybrid": [], "fts": [], "vector": []}
    with engine.begin() as conn:
        load_index(conn, chunks, cv.vectors)
        for q in qs:
            for mode in runs:
                res = search(conn, q["question"], emb, k=TOP_K, mode=mode)  # type: ignore[arg-type]
                runs[mode].append(
                    {
                        "id": q["id"],
                        "language": q["language"],
                        "answerable": q["answerable"],
                        "gold": q["gold"],
                        "ranked": [h.id for h in res.hits],
                        "best_cosine": res.best_cosine,
                        "n_hits": len(res.hits),
                    }
                )
    engine.dispose()

    # tau on the dev questions only (hybrid mode's best vector cosine).
    dev = [r for r in runs["hybrid"] if is_dev(r["id"])]
    test = [r for r in runs["hybrid"] if not is_dev(r["id"])]

    def balanced(rows: list[dict[str, Any]], tau: float) -> float:
        a = [r for r in rows if r["answerable"]]
        u = [r for r in rows if not r["answerable"]]
        kept = sum((r["best_cosine"] or 0) >= tau for r in a) / len(a)
        rejected = sum((r["best_cosine"] or 0) < tau for r in u) / len(u)
        return (kept + rejected) / 2

    scores = {t: balanced(dev, t) for t in GRID}
    tau = max(GRID, key=lambda t: (scores[t], -t))
    THRESHOLD.write_text(
        json.dumps(
            {
                "tau": tau,
                "chosen_on": "dev questions only (agents/rag/EVAL_RULE.md)",
                "rule_sha256": _sha(RULE),
                "questions_sha256": _sha(QUESTIONS),
            },
            indent=1,
        )
        + "\n"
    )

    def no_source(rows: list[dict[str, Any]]) -> dict[str, Any]:
        a = [r for r in rows if r["answerable"]]
        u = [r for r in rows if not r["answerable"]]
        rej_u = sum((r["best_cosine"] or 0) < tau for r in u)
        rej_a = sum((r["best_cosine"] or 0) < tau for r in a)
        rejected = rej_u + rej_a
        return {
            "n_unanswerable": len(u),
            "unanswerable_rejected": rej_u,
            "answerable_wrongly_rejected": rej_a,
            "no_source_recall": round(rej_u / len(u), 4) if u else None,
            "no_source_precision": round(rej_u / rejected, 4) if rejected else None,
        }

    by_mode = {m: _metrics([r for r in rows if not is_dev(r["id"])]) for m, rows in runs.items()}
    by_lang = {
        mode: {
            lang: _metrics([r for r in rows if not is_dev(r["id"]) and r["language"] == lang])
            for lang in ("de", "en")
        }
        for mode, rows in runs.items()
    }
    hyb = by_mode["hybrid"]
    other = max(by_mode["fts"]["recall@5"], by_mode["vector"]["recall@5"])
    singles = {"vector": by_mode["vector"]["recall@5"], "fts": by_mode["fts"]["recall@5"]}
    if hyb["recall@5"] >= other:
        served = {"method": "hybrid", "basis": "the pre-registered check passed"}
    else:
        best = max(singles, key=lambda k: singles[k])
        served = {
            "method": best,
            "basis": (
                "the pre-registered check 'hybrid at least as good as the better single method' "
                f"failed; the single method with the higher test recall@5 ({best}) is served. "
                "This choice was made after the results were known (EVAL_RULE.md says only that "
                "the failure is reported); hybrid stays available as RAG_RETRIEVAL=hybrid"
            ),
        }
    served_rows = [r for r in runs[served["method"]] if not is_dev(r["id"])]
    misses = [
        {"id": r["id"], "gold": r["gold"], "top": r["ranked"][:3]}
        for r in served_rows
        if r["answerable"] and not any(i in r["gold"] for i in r["ranked"][:5])
    ]
    result = {
        "component": "RAG rulebook (ARCHITECTURE §11)",
        "served": served,
        "settings": {
            "rrf_k": RRF_K,
            "candidates_per_list": 50,
            "top_k": TOP_K,
            "embedding": vectors.read_manifest()["model"],
        },
        "data": {
            "corpus_sha256": corpus_hash(chunks),
            "chunks": len(chunks),
            "questions": len(qs),
            "questions_sha256": _sha(QUESTIONS),
            "rule_sha256": _sha(RULE),
            "vectors_manifest_sha256": _sha(vectors.EMBED_DIR / "manifest.json"),
            "dev_questions": len(dev),
            "test_questions": len(test),
        },
        "no_source_threshold": {
            "tau": tau,
            "dev_balanced_accuracy_by_tau": {str(k): round(v, 4) for k, v in scores.items()},
        },
        "test": {
            "hybrid": hyb,
            "by_language": by_lang,
            "no_source": no_source(test),
            "modes": by_mode,
            "misses_at_5": misses,
        },
        "dev": {"hybrid": _metrics(dev)},
        "checks": {
            "hybrid_recall@5_at_least_0.80": hyb["recall@5"] >= 0.80,
            "hybrid_recall@5_at_least_best_single": hyb["recall@5"] >= other,
        },
        "caveats": [
            "Questions were written by the author of the corpus; they are easier than questions "
            "from strangers.",
            "Gold passages include synthetic documents written for this prototype.",
            "Vectors are from the int8 ONNX export of bge-m3.",
        ],
        "environment": {
            "git_commit": _git("rev-parse", "HEAD"),
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
    }
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: result["test"][k] for k in ("hybrid", "no_source")}, indent=1))
    print("tau", tau, result["checks"])


if __name__ == "__main__":
    main()
