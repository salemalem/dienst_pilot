"""Embeddings: bge-m3 on ONNX Runtime, served locally, behind a small port.

The model is the int8-quantised ONNX export of BAAI/bge-m3 (Xenova/bge-m3, ``sentence_transformers_
quantized.onnx``): 1024 dimensions, CLS pooling, L2-normalised. Nothing leaves the machine.
CI never loads it: it uses the vectors committed in ``agents/rag/embeddings/`` (``Precomputed``).
"""

import glob
import hashlib
import os
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from dienstpilot_agents.rag.corpus import text_hash

DIMENSIONS = 1024
MODEL_NAME = "BAAI/bge-m3 (ONNX int8, Xenova/bge-m3)"
MODEL_FILE = "onnx/sentence_transformers_quantized.onnx"
DEFAULT_GLOB = "~/.cache/huggingface/hub/models--Xenova--bge-m3/snapshots/*"
MAX_TOKENS = 512


class Embedder(Protocol):
    """Turns texts into unit vectors of 1024 numbers."""

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return a (len(texts), 1024) float32 array."""


class ModelUnavailableError(RuntimeError):
    """The ONNX model files are not on this machine."""


def find_model_dir(path: str | None = None) -> Path:
    """Return the model directory (``RAG_MODEL_DIR``, else the Hugging Face cache)."""
    pattern = path or os.environ.get("RAG_MODEL_DIR") or DEFAULT_GLOB
    matches = sorted(glob.glob(os.path.expanduser(pattern)))
    for m in matches:
        if (Path(m) / MODEL_FILE).exists() and (Path(m) / "tokenizer.json").exists():
            return Path(m)
    raise ModelUnavailableError(f"bge-m3 ONNX files not found ({pattern})")


def model_digest(model_dir: Path) -> str:
    """Return the SHA-256 of the ONNX file (recorded with the committed vectors)."""
    h = hashlib.sha256()
    with (model_dir / MODEL_FILE).open("rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


class OnnxBgeM3:
    """The real embedder. Loads lazily; one text per run."""

    def __init__(self, model_dir: Path | None = None) -> None:
        """Remember where the model is; nothing is loaded yet."""
        self._dir = model_dir
        self._session: Any = None
        self._tokenizer: Any = None

    def _load(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer

        d = self._dir or find_model_dir()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
        self._session = ort.InferenceSession(
            str(d / MODEL_FILE), opts, providers=["CPUExecutionProvider"]
        )
        tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        tok.enable_padding()
        tok.enable_truncation(MAX_TOKENS)
        self._tokenizer = tok

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed texts one by one (L2-normalised sentence embeddings)."""
        self._load()
        assert self._session is not None and self._tokenizer is not None
        out = []
        # One text per call: with this int8 export the padding of a batch changes the vectors
        # (cosine about 0.98 against the unpadded ones), so documents and queries must both be
        # embedded unpadded to be comparable.
        for i in range(len(texts)):
            enc = self._tokenizer.encode_batch(texts[i : i + 1])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            res = self._session.run(
                ["sentence_embedding"], {"input_ids": ids, "attention_mask": mask}
            )
            out.append(np.asarray(res[0], dtype=np.float32))
        v = np.vstack(out) if out else np.zeros((0, DIMENSIONS), dtype=np.float32)
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        return np.asarray(v / np.where(norms == 0, 1, norms), dtype=np.float32)


class Precomputed:
    """Vectors committed with the repository, looked up by the SHA-256 of the text.

    Used by CI and by tests: no model is loaded. A text that has no committed vector raises, so a
    test can never silently fall back to something else.
    """

    def __init__(self, texts: list[str], vectors: np.ndarray) -> None:
        """Index ``vectors[i]`` by the hash of ``texts[i]``."""
        self._by_hash = {text_hash(t): vectors[i] for i, t in enumerate(texts)}

    def has(self, text: str) -> bool:
        """Tell whether a vector for this text is committed."""
        return text_hash(text) in self._by_hash

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return the committed vectors."""
        try:
            return np.vstack([self._by_hash[text_hash(t)] for t in texts]).astype(np.float32)
        except KeyError as e:
            raise ModelUnavailableError("no committed vector for this text") from e
