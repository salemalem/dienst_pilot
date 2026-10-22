"""The rulebook (RAG): search with citations, read one passage (ARCHITECTURE §11, ADR-019)."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from dienstpilot.app.context import CtxDep
from dienstpilot.app.deps import OversightReaderDep
from dienstpilot.shared.settings import Settings, get_settings
from dienstpilot_agents.rag.embedder import (
    Embedder,
    ModelUnavailableError,
    OnnxBgeM3,
    find_model_dir,
)
from dienstpilot_agents.rag.search import TOP_K, Hit, Mode, search
from dienstpilot_agents.rag.search import get_chunk as _get_chunk
from dienstpilot_agents.rag.threshold import no_source_cosine

router = APIRouter(tags=["rules"])


class Passage(BaseModel):
    """One citable unit of text."""

    id: str
    citation: str
    section: str
    paragraph: int
    heading: str
    text: str
    language: str
    synthetic: bool = Field(description="True for documents written for this prototype")
    score: float
    cosine: float | None


class RuleSearch(BaseModel):
    """Search result. ``found`` is false when no passage supports an answer."""

    query: str
    found: bool
    passages: list[Passage]
    mode: str = Field(description="What actually ran: vector, hybrid or fts-only")
    configured: str = Field(
        description="What is configured (RAG_RETRIEVAL); the champion is vector"
    )
    fallback: bool = Field(description="True when the model is missing and full-text ran instead")
    vector_used: bool


@lru_cache
def get_embedder() -> Embedder | None:
    """Return the local bge-m3 embedder, or None if the model files are not on this machine."""
    try:
        directory = find_model_dir(get_settings().bge_m3_dir)
    except ModelUnavailableError:
        return None
    return OnnxBgeM3(directory)


EmbedderDep = Annotated[Embedder | None, Depends(get_embedder)]


def _passage(h: Hit) -> Passage:
    return Passage(
        id=h.id,
        citation=h.citation,
        section=h.section,
        paragraph=h.paragraph,
        heading=h.heading,
        text=h.text,
        language=h.language,
        synthetic=h.synthetic,
        score=round(h.score, 5),
        cosine=None if h.cosine is None else round(h.cosine, 4),
    )


@router.get("/rules/search")
def search_rules(
    c: CtxDep,
    _: OversightReaderDep,
    embedder: EmbedderDep,
    settings: Annotated[Settings, Depends(get_settings)],
    q: Annotated[str, Query(min_length=3, max_length=400)],
    k: Annotated[int, Query(ge=1, le=10)] = TOP_K,
) -> RuleSearch:
    """Search the rulebook (German and English questions). Every passage carries its citation."""
    configured = settings.rag_retrieval
    # The served method is the evaluated champion (vector); without the model files, full-text.
    run: Mode = configured if embedder is not None or configured == "fts" else "fts"
    res = search(c.session, q, embedder, k=k, mode=run)
    # Below the frozen cosine threshold of the best vector hit no source is claimed (chosen on the
    # dev questions of the RAG evaluation: agents/rag/EVAL_RULE.md). Without vectors (no model on
    # this machine) the threshold cannot be applied, and full-text hits count as found.
    tau = no_source_cosine()
    found = bool(res.hits) and (res.best_cosine is None or tau is None or res.best_cosine >= tau)
    return RuleSearch(
        query=q,
        found=found,
        passages=[_passage(h) for h in res.hits] if found else [],
        mode=run if res.vector_used else "fts-only",
        configured=configured,
        fallback=not res.vector_used and configured != "fts",
        vector_used=res.vector_used,
    )


@router.get("/rules/{chunk_id:path}")
def get_rule(c: CtxDep, _: OversightReaderDep, chunk_id: str) -> Passage:
    """Return one passage by its id, for example ``arbzg:§5:1``."""
    h = _get_chunk(c.session, chunk_id)
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return _passage(h)
