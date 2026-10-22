"""Command line: build or check the committed vectors, and load the index.

python -m dienstpilot_agents.rag.index embed     # needs the model (local only); rewrites vectors
python -m dienstpilot_agents.rag.index check     # corpus text vs committed vectors (no model)
python -m dienstpilot_agents.rag.index load      # committed vectors into the database
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine

from dienstpilot_agents.rag import vectors
from dienstpilot_agents.rag.corpus import corpus_hash, load_corpus
from dienstpilot_agents.rag.embedder import OnnxBgeM3, find_model_dir, model_digest
from dienstpilot_agents.rag.store import load_index


def chunk_vectors() -> tuple[list, "vectors.VectorSet"]:  # type: ignore[type-arg]
    """Return the chunks and their committed vectors (raises if the corpus changed)."""
    _, chunks = load_corpus()
    return chunks, vectors.load("chunks", [c.embed_text for c in chunks])


def embed() -> None:
    """Embed the corpus with the real model and write the committed vectors."""
    _, chunks = load_corpus()
    model = OnnxBgeM3()
    vecs = vectors.embed_chunks(chunks, model)
    texts = [c.embed_text for c in chunks]
    vectors.write("chunks", texts, vecs, {"ids": [c.id for c in chunks]})
    vectors.write_manifest(chunks, model_digest(find_model_dir()))
    print(f"embedded {len(chunks)} chunks; corpus {corpus_hash(chunks)[:12]}")


def embed_questions(path: Path) -> None:
    """Embed the evaluation questions with the real model (committed, so CI needs no model)."""
    texts = [q["question"] for q in json.loads(path.read_text(encoding="utf-8"))["questions"]]
    vecs = OnnxBgeM3().embed(texts)
    vectors.write("questions", texts, vecs)
    _, chunks = load_corpus()
    vectors.write_manifest(
        chunks,
        model_digest(find_model_dir()),
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    print(f"embedded {len(texts)} questions")


def check() -> int:
    """Exit non-zero when the committed vectors do not belong to the current corpus."""
    try:
        chunk_vectors()
    except ValueError as e:
        print(e)
        return 1
    manifest = vectors.read_manifest()
    _, chunks = load_corpus()
    if manifest["corpus_sha256"] != corpus_hash(chunks):
        print("manifest does not match the corpus: run `make rag-embed`")
        return 1
    print("vectors match the corpus")
    return 0


def load(url: str) -> None:
    """Load the committed vectors into the database at ``url``."""
    chunks, vs = chunk_vectors()
    engine = create_engine(url)
    with engine.begin() as conn:
        n = load_index(conn, chunks, vs.vectors)
    engine.dispose()
    print(f"indexed {n} chunks")


def main() -> None:
    """Dispatch the sub-command."""
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["embed", "embed-questions", "check", "load"])
    ap.add_argument("--database-url")
    ap.add_argument("--questions", default="eval/rag_questions.json")
    args = ap.parse_args()
    if args.command == "embed":
        embed()
    elif args.command == "embed-questions":
        embed_questions(Path(args.questions))
    elif args.command == "check":
        sys.exit(check())
    else:
        url = args.database_url or os.environ.get("DATABASE_URL")
        if not url:
            sys.exit("give --database-url or set DATABASE_URL")
        load(url)


if __name__ == "__main__":
    main()
