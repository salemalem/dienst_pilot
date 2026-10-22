"""The rulebook index (expand-only: new schema ``rag``).

One table of paragraph chunks with a German and an English full-text vector and a 1024-dimension
bge-m3 embedding (pgvector, HNSW, cosine). The index is built from the committed corpus and
vectors (``make rag-index``); the table holds nothing the repository cannot rebuild.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-23 09:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS rag")
    op.execute(
        """
        CREATE TABLE rag.chunk (
            id text PRIMARY KEY,
            doc_id text NOT NULL,
            doc_title text NOT NULL,
            doc_version text NOT NULL,
            language varchar(2) NOT NULL,
            synthetic boolean NOT NULL,
            section text NOT NULL,
            heading text NOT NULL,
            paragraph integer NOT NULL,
            text text NOT NULL,
            embed_text text NOT NULL,
            citation text NOT NULL,
            tsv_de tsvector NOT NULL,
            tsv_en tsvector NOT NULL,
            embedding vector(1024) NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_rag_chunk_tsv_de ON rag.chunk USING gin (tsv_de)")
    op.execute("CREATE INDEX ix_rag_chunk_tsv_en ON rag.chunk USING gin (tsv_en)")
    op.execute(
        "CREATE INDEX ix_rag_chunk_embedding ON rag.chunk USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE TABLE rag.state (key text PRIMARY KEY, value text NOT NULL)")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS rag CASCADE")
