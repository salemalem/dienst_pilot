"""Documents and chunks.

A corpus document is Markdown with a small front matter. Sections start with ``## [label] heading``
(label: ``§ 5``, ``Regel 2``, ``SOP-1``), paragraphs with ``(n)``. One chunk is one paragraph, so a
citation such as ``ArbZG § 5 Abs. 1`` always points at a real unit of text.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parents[3] / "rag" / "corpus"
_SECTION = re.compile(r"^##\s+\[(?P<label>[^\]]+)\]\s*(?P<heading>.*)$")
_PARA = re.compile(r"^\((?P<n>\d+)\)\s+(?P<text>.*)$")


@dataclass(frozen=True)
class Document:
    """One corpus document with the metadata a citation needs."""

    id: str
    title: str
    language: str
    synthetic: bool
    version: str
    source: str
    retrieved: str
    body: str


@dataclass(frozen=True)
class Chunk:
    """One paragraph of one section of one document."""

    id: str
    doc_id: str
    doc_title: str
    doc_version: str
    language: str
    synthetic: bool
    section: str
    heading: str
    paragraph: int
    text: str

    @property
    def embed_text(self) -> str:
        """The text that is embedded and full-text indexed: the paragraph with its context."""
        return f"{self.doc_title} {self.section} {self.heading}\n{self.text}"

    @property
    def citation(self) -> str:
        """Return a human citation, e.g. ``ArbZG § 5 Abs. 1 (Stand 2024-12-31)``."""
        para = f" Abs. {self.paragraph}" if self.paragraph else ""
        kind = " [synthetisch]" if self.synthetic and self.language == "de" else ""
        kind = " [synthetic]" if self.synthetic and self.language == "en" else kind
        return f"{self.doc_title} {self.section}{para} ({self.doc_version}){kind}"


def parse_document(path: Path) -> Document:
    """Read a corpus file (front matter, then the body)."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path.name}: missing front matter")
    head, _, body = raw[4:].partition("\n---\n")
    meta: dict[str, str] = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    required = {"id", "title", "language", "synthetic", "version", "source", "retrieved"}
    if missing := required - set(meta):
        raise ValueError(f"{path.name}: front matter lacks {sorted(missing)}")
    return Document(
        id=meta["id"],
        title=meta["title"],
        language=meta["language"],
        synthetic=meta["synthetic"].lower() == "true",
        version=meta["version"],
        source=meta["source"],
        retrieved=meta["retrieved"],
        body=body,
    )


def chunk_document(doc: Document) -> list[Chunk]:
    """Split a document into paragraph chunks with stable ids like ``arbzg:§5:1``."""
    chunks: list[Chunk] = []
    section = heading = ""
    para = 0
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        text = " ".join(" ".join(buf).split())
        if section and text and text != "(weggefallen)":
            label = section.replace(" ", "")
            chunks.append(
                Chunk(
                    id=f"{doc.id}:{label}:{para}",
                    doc_id=doc.id,
                    doc_title=doc.title,
                    doc_version=doc.version,
                    language=doc.language,
                    synthetic=doc.synthetic,
                    section=section,
                    heading=heading,
                    paragraph=para,
                    text=text,
                )
            )
        buf = []

    for line in doc.body.splitlines():
        if m := _SECTION.match(line):
            flush()
            section, heading, para = m["label"].strip(), m["heading"].strip(), 0
        elif not line.strip():
            continue
        elif m := _PARA.match(line.strip()):
            flush()
            para = int(m["n"])
            buf = [m["text"]]
        else:
            if para == 0 and not buf:
                para = 1
            buf.append(line.strip())
    flush()
    return chunks


def load_corpus(directory: Path = CORPUS_DIR) -> tuple[list[Document], list[Chunk]]:
    """Load every document and chunk of the corpus, in a fixed order."""
    docs = [parse_document(p) for p in sorted(directory.glob("*.md"))]
    chunks = [c for d in docs for c in chunk_document(d)]
    ids = [c.id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate chunk ids in the corpus")
    return docs, chunks


def corpus_hash(chunks: list[Chunk]) -> str:
    """Return a SHA-256 over every chunk id and embedded text (changes with any corpus edit)."""
    h = hashlib.sha256()
    for c in sorted(chunks, key=lambda c: c.id):
        h.update(c.id.encode())
        h.update(b"\0")
        h.update(c.embed_text.encode())
        h.update(b"\0")
    return h.hexdigest()


def text_hash(text: str) -> str:
    """Return the SHA-256 of a text (the key of precomputed vectors)."""
    return hashlib.sha256(text.encode()).hexdigest()
