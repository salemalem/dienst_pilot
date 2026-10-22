"""The chunk table (schema ``rag``, created by migration 0011) and loading the corpus into it."""

import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from dienstpilot_agents.rag.corpus import Chunk, corpus_hash


def _vec(v: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in v) + "]"


def load_index(conn: Connection | Session, chunks: list[Chunk], vectors: np.ndarray) -> int:
    """Replace the whole index with these chunks and their vectors."""
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors differ in length")
    conn.execute(text("TRUNCATE rag.chunk"))
    conn.execute(
        text(
            "INSERT INTO rag.chunk (id, doc_id, doc_title, doc_version, language, synthetic,"
            " section, heading, paragraph, text, embed_text, citation, tsv_de, tsv_en, embedding)"
            " VALUES (:id, :doc_id, :doc_title, :doc_version, :language, :synthetic, :section,"
            " :heading, :paragraph, :text, :embed_text, :citation,"
            " to_tsvector('german', :embed_text), to_tsvector('english', :embed_text),"
            " CAST(:embedding AS vector))"
        ),
        [
            {
                "id": c.id,
                "doc_id": c.doc_id,
                "doc_title": c.doc_title,
                "doc_version": c.doc_version,
                "language": c.language,
                "synthetic": c.synthetic,
                "section": c.section,
                "heading": c.heading,
                "paragraph": c.paragraph,
                "text": c.text,
                "embed_text": c.embed_text,
                "citation": c.citation,
                "embedding": _vec(vectors[i]),
            }
            for i, c in enumerate(chunks)
        ],
    )
    conn.execute(
        text(
            "INSERT INTO rag.state (key, value) VALUES ('corpus_sha256', :h)"
            " ON CONFLICT (key) DO UPDATE SET value = :h"
        ),
        {"h": corpus_hash(chunks)},
    )
    return len(chunks)


def indexed_corpus_hash(conn: Connection | Session) -> str | None:
    """Return the corpus hash the index was built from (None: empty)."""
    return conn.execute(text("SELECT value FROM rag.state WHERE key = 'corpus_sha256'")).scalar()
