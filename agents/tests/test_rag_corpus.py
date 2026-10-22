"""The corpus, its chunks and the committed vectors (no database, no model)."""

import hashlib
import json
from pathlib import Path

import numpy as np

from dienstpilot_agents.rag import vectors
from dienstpilot_agents.rag.arbzg import SOURCE_DIR, convert
from dienstpilot_agents.rag.corpus import (
    CORPUS_DIR,
    chunk_document,
    corpus_hash,
    load_corpus,
    parse_document,
    text_hash,
)
from dienstpilot_agents.rag.embedder import DIMENSIONS

REPO = Path(__file__).resolve().parents[2]


def test_every_document_says_where_it_comes_from_and_whether_it_is_synthetic() -> None:
    docs, _ = load_corpus()
    assert {d.id for d in docs} == {"arbzg", "regeln", "rules", "bv", "bv-en", "sop", "sop-en"}
    for d in docs:
        assert d.version and d.source and d.retrieved
        if d.id == "arbzg":
            assert not d.synthetic and d.source.startswith("https://www.gesetze-im-internet.de/")
            assert d.version.startswith("Stand ")
        else:
            assert d.synthetic, f"{d.id} is written for this prototype and must say so"
            assert "synthetic" in d.body.lower() or "synthetisch" in d.body.lower()


def test_no_collective_agreement_text_is_in_the_corpus() -> None:
    docs, _ = load_corpus()
    assert any("kein Tarifvertragstext" in d.source for d in docs)


def test_the_statute_text_is_the_official_xml_unchanged() -> None:
    xml = SOURCE_DIR / "arbzg.xml"
    pinned = (SOURCE_DIR / "arbzg.xml.sha256").read_text().split()[0]
    assert hashlib.sha256(xml.read_bytes()).hexdigest() == pinned
    doc = parse_document(CORPUS_DIR / "arbzg.de.md")
    regenerated = convert(xml, doc.retrieved)
    assert regenerated == (CORPUS_DIR / "arbzg.de.md").read_text(encoding="utf-8")


def test_chunks_are_paragraphs_with_real_citations() -> None:
    _, chunks = load_corpus()
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    rest = next(c for c in chunks if c.id == "arbzg:§5:1")
    assert "elf Stunden" in rest.text
    assert rest.citation == "Arbeitszeitgesetz (ArbZG) § 5 Abs. 1 (Stand 2024-12-31)"
    synthetic = next(c for c in chunks if c.id == "regeln:Regel2:1")
    assert synthetic.citation.endswith("[synthetisch]")
    assert not any(c.text == "(weggefallen)" for c in chunks)


def test_chunker_splits_on_sections_and_paragraphs(tmp_path: Path) -> None:
    f = tmp_path / "t.md"
    f.write_text(
        '---\nid: t\ntitle: T\nlanguage: de\nsynthetic: true\nversion: "v1"\nsource: s\n'
        "retrieved: 2026-10-22\n---\n\n## [§ 1] Eins\nErster Satz\nzweite Zeile.\n\n"
        "## [§ 2] Zwei\n(1) Absatz eins.\n(2) Absatz zwei,\nweiter.\n",
        encoding="utf-8",
    )
    chunks = chunk_document(parse_document(f))
    assert [(c.id, c.text) for c in chunks] == [
        ("t:§1:1", "Erster Satz zweite Zeile."),
        ("t:§2:1", "Absatz eins."),
        ("t:§2:2", "Absatz zwei, weiter."),
    ]


def test_committed_vectors_belong_to_this_corpus() -> None:
    """CI never loads the model: a corpus edit without `make rag-embed` fails here."""
    _, chunks = load_corpus()
    manifest = vectors.read_manifest()
    assert manifest["corpus_sha256"] == corpus_hash(chunks)
    assert manifest["chunks"] == len(chunks)
    npy = vectors.EMBED_DIR / "chunks.npy"
    assert hashlib.sha256(npy.read_bytes()).hexdigest() == manifest["chunks_npy_sha256"]
    vs = vectors.load("chunks", [c.embed_text for c in chunks])
    assert vs.vectors.shape == (len(chunks), DIMENSIONS)
    np.testing.assert_allclose(np.linalg.norm(vs.vectors, axis=1), 1.0, atol=1e-3)


def test_committed_question_vectors_belong_to_the_question_file() -> None:
    q = REPO / "eval" / "rag_questions.json"
    manifest = vectors.read_manifest()
    assert hashlib.sha256(q.read_bytes()).hexdigest() == manifest["questions_json_sha256"]
    texts = [x["question"] for x in json.loads(q.read_text(encoding="utf-8"))["questions"]]
    assert vectors.read_hashes("questions") == [text_hash(t) for t in texts]
    assert (
        len(texts) == 60
        and sum(1 for x in json.loads(q.read_text())["questions"] if x["answerable"]) == 52
    )


def test_the_evaluation_result_belongs_to_these_files() -> None:
    """rag.json must be regenerated when the corpus, the questions or the rule change."""
    r = json.loads((REPO / "eval" / "results" / "rag.json").read_text(encoding="utf-8"))
    _, chunks = load_corpus()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    assert r["data"]["corpus_sha256"] == corpus_hash(chunks)
    assert r["data"]["questions_sha256"] == sha(REPO / "eval" / "rag_questions.json")
    assert r["data"]["rule_sha256"] == sha(REPO / "agents" / "rag" / "EVAL_RULE.md")
    assert r["data"]["vectors_manifest_sha256"] == sha(vectors.EMBED_DIR / "manifest.json")
    tau = json.loads((REPO / "agents" / "rag" / "threshold.json").read_text())["tau"]
    assert tau == r["no_source_threshold"]["tau"]
