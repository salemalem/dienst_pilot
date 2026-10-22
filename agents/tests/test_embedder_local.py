"""The real model reproduces the committed vectors (skipped where the model is not installed)."""

import numpy as np
import pytest

from dienstpilot_agents.rag import vectors
from dienstpilot_agents.rag.corpus import load_corpus
from dienstpilot_agents.rag.embedder import (
    ModelUnavailableError,
    OnnxBgeM3,
    Precomputed,
    find_model_dir,
)


def test_the_model_reproduces_the_committed_vectors() -> None:
    try:
        find_model_dir()
    except ModelUnavailableError:
        pytest.skip("bge-m3 ONNX files are not on this machine")
    _, chunks = load_corpus()
    committed = vectors.load("chunks", [c.embed_text for c in chunks])
    sample = list(range(0, len(chunks), 23))
    fresh = OnnxBgeM3().embed([chunks[i].embed_text for i in sample])
    cos = np.sum(fresh * committed.vectors[sample], axis=1)
    assert cos.min() >= 0.999


def test_a_text_without_a_committed_vector_is_refused() -> None:
    p = Precomputed(["a"], np.ones((1, 4), dtype=np.float32))
    assert p.has("a") and not p.has("b")
    with pytest.raises(ModelUnavailableError):
        p.embed(["b"])
