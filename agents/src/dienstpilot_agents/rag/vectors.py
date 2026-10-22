"""The committed vectors: ``agents/rag/embeddings/`` (chunks, eval questions, manifest)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from dienstpilot_agents.rag.corpus import CORPUS_DIR, Chunk, corpus_hash, text_hash
from dienstpilot_agents.rag.embedder import DIMENSIONS, MODEL_NAME, Embedder, Precomputed

EMBED_DIR = CORPUS_DIR.parent / "embeddings"


@dataclass(frozen=True)
class VectorSet:
    """Texts and their vectors, with the hashes that bind them together."""

    texts: list[str]
    vectors: np.ndarray

    def embedder(self) -> Precomputed:
        """Return a lookup embedder over these vectors."""
        return Precomputed(self.texts, self.vectors)


def _npy_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(
    name: str, texts: list[str], vectors: np.ndarray, extra: dict[str, Any] | None = None
) -> None:
    """Write ``<name>.npy`` and ``<name>.json`` (the text hashes) into the embeddings folder."""
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMBED_DIR / f"{name}.npy", vectors.astype(np.float32))
    meta = {"text_sha256": [text_hash(t) for t in texts], "dimensions": DIMENSIONS, **(extra or {})}
    (EMBED_DIR / f"{name}.json").write_text(json.dumps(meta, indent=1) + "\n")


def read_hashes(name: str) -> list[str]:
    """Return the text hashes of a committed set."""
    meta = json.loads((EMBED_DIR / f"{name}.json").read_text())
    return list(meta["text_sha256"])


def load(name: str, texts: list[str]) -> VectorSet:
    """Load a committed set for exactly these texts (in this order); refuse if they differ."""
    hashes = read_hashes(name)
    if hashes != [text_hash(t) for t in texts]:
        raise ValueError(f"the committed vectors '{name}' do not match the current texts")
    vectors = np.load(EMBED_DIR / f"{name}.npy")
    return VectorSet(texts, vectors)


def write_manifest(
    chunks: list[Chunk], model_sha256: str, questions_sha256: str | None = None
) -> None:
    """Record what the vectors were made from (model, corpus) and their own hashes."""
    manifest = {
        "model": MODEL_NAME,
        "model_file_sha256": model_sha256,
        "corpus_sha256": corpus_hash(chunks),
        "chunks": len(chunks),
        "chunks_npy_sha256": _npy_hash(EMBED_DIR / "chunks.npy"),
        "questions_json_sha256": questions_sha256,
        "questions_npy_sha256": _npy_hash(EMBED_DIR / "questions.npy")
        if (EMBED_DIR / "questions.npy").exists()
        else None,
    }
    (EMBED_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")


def read_manifest() -> dict[str, str | int | None]:
    """Return the manifest."""
    return json.loads((EMBED_DIR / "manifest.json").read_text())  # type: ignore[no-any-return]


def embed_chunks(chunks: list[Chunk], embedder: Embedder) -> np.ndarray:
    """Embed every chunk's text with the given embedder."""
    return embedder.embed([c.embed_text for c in chunks])
