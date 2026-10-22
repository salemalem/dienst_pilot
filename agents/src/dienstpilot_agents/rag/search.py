"""Hybrid retrieval: Postgres full-text and pgvector, fused by reciprocal rank (k = 60).

Fixed before the evaluation (``agents/rag/EVAL_RULE.md``): RRF constant 60, 50 candidates per
list, top 5 returned. Without an embedder (or without the model) it falls back to full-text only
and says so (``vector_used`` is False), never silently.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from dienstpilot_agents.rag.embedder import Embedder, ModelUnavailableError
from dienstpilot_agents.rag.store import _vec

RRF_K = 60
CANDIDATES = 50
TOP_K = 5
Mode = Literal["hybrid", "fts", "vector"]
_WORD = re.compile(r"[\wäöüßÄÖÜ]{3,}", re.UNICODE)


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk with its citation."""

    id: str
    doc_id: str
    citation: str
    section: str
    paragraph: int
    heading: str
    text: str
    language: str
    synthetic: bool
    score: float
    fts_rank: int | None
    vector_rank: int | None
    cosine: float | None


@dataclass(frozen=True)
class SearchResult:
    """The hits and what was used to find them."""

    hits: list[Hit]
    mode: str
    vector_used: bool
    best_cosine: float | None


def _hit(
    r: Any, score: float, fts_rank: int | None, vector_rank: int | None, cosine: float | None
) -> Hit:
    return Hit(
        id=r[0],
        doc_id=r[1],
        citation=r[2],
        section=r[3],
        paragraph=r[4],
        heading=r[5],
        text=r[6],
        language=r[7],
        synthetic=r[8],
        score=score,
        fts_rank=fts_rank,
        vector_rank=vector_rank,
        cosine=cosine,
    )


def _or_query(q: str) -> str:
    words = sorted({w.lower() for w in _WORD.findall(q)})
    return " | ".join(words)


def _fts(conn: Connection | Session, q: str) -> list[str]:
    tsq = _or_query(q)
    if not tsq:
        return []
    rows = conn.execute(
        text(
            "SELECT id FROM rag.chunk, to_tsquery('german', :q) qd, to_tsquery('english', :q) qe"
            " WHERE tsv_de @@ qd OR tsv_en @@ qe"
            " ORDER BY GREATEST(ts_rank_cd(tsv_de, qd), ts_rank_cd(tsv_en, qe)) DESC, id"
            " LIMIT :n"
        ),
        {"q": tsq, "n": CANDIDATES},
    )
    return [r[0] for r in rows]


def _vector(conn: Connection | Session, vec: str) -> list[tuple[str, float]]:
    rows = conn.execute(
        text(
            "SELECT id, 1 - (embedding <=> CAST(:v AS vector)) AS cos FROM rag.chunk"
            " ORDER BY embedding <=> CAST(:v AS vector), id LIMIT :n"
        ),
        {"v": vec, "n": CANDIDATES},
    )
    return [(r[0], float(r[1])) for r in rows]


def search(
    conn: Connection | Session,
    query: str,
    embedder: Embedder | None,
    *,
    k: int = TOP_K,
    mode: Mode = "hybrid",
) -> SearchResult:
    """Return the top ``k`` chunks for a question (German or English)."""
    fts_ids = _fts(conn, query) if mode in ("hybrid", "fts") else []
    vec_hits: list[tuple[str, float]] = []
    used = False
    if mode in ("hybrid", "vector") and embedder is not None:
        try:
            vec_hits = _vector(conn, _vec(embedder.embed([query])[0]))
            used = True
        except ModelUnavailableError:
            used = False
    fts_rank = {cid: i + 1 for i, cid in enumerate(fts_ids)}
    vec_rank = {cid: i + 1 for i, (cid, _) in enumerate(vec_hits)}
    cos = dict(vec_hits)
    ids = set(fts_rank) | set(vec_rank)
    score = {
        cid: (1 / (RRF_K + fts_rank[cid]) if cid in fts_rank else 0.0)
        + (1 / (RRF_K + vec_rank[cid]) if cid in vec_rank else 0.0)
        for cid in ids
    }
    top = sorted(ids, key=lambda c: (-score[c], c))[:k]
    if not top:
        return SearchResult([], mode, used, None)
    rows = conn.execute(
        text(
            "SELECT id, doc_id, citation, section, paragraph, heading, text, language, synthetic"
            " FROM rag.chunk WHERE id = ANY(:ids)"
        ),
        {"ids": top},
    ).all()
    by = {r[0]: r for r in rows}
    hits = [
        _hit(by[cid], score[cid], fts_rank.get(cid), vec_rank.get(cid), cos.get(cid)) for cid in top
    ]
    return SearchResult(hits, mode, used, max(cos.values()) if cos else None)


def get_chunk(conn: Connection | Session, chunk_id: str) -> Hit | None:
    """Return one chunk by its id (for ``get_rule``)."""
    r = conn.execute(
        text(
            "SELECT id, doc_id, citation, section, paragraph, heading, text, language, synthetic"
            " FROM rag.chunk WHERE id = :i"
        ),
        {"i": chunk_id},
    ).first()
    return None if r is None else _hit(r, 1.0, None, None, None)
