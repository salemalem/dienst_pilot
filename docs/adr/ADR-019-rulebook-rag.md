# ADR-019: The rulebook: corpus, chunks, local embeddings, hybrid retrieval, CI without the model

- Status: Accepted
- Date: 2026-10-23
- Phase: 10a (MCP servers and RAG)

## Decision

1. **Corpus** (`agents/rag/corpus/`): the official ArbZG (gesetze-im-internet.de XML, kept with its SHA-256 in `agents/rag/source/`, converted word for word by `dienstpilot_agents.rag.arbzg`, version "Stand 2024-12-31", retrieved 2026-10-22; an official statute is free to use under § 5 UrhG) plus synthetic documents written for the prototype: the department rulebook (a test checks its numbers against the seeded rule set), an example works agreement and department SOPs, each in German and English. Synthetic documents say so in the front matter and the body, and their citations are marked. No collective-agreement text.
2. **Chunks** are paragraphs (Absatz) of sections (§), with ids such as `arbzg:§5:1`; a citation is built from the document title, section, paragraph and version, so it always points at a real unit of text.
3. **Embeddings:** bge-m3 as the int8 ONNX export (`Xenova/bge-m3`) on ONNX Runtime with `tokenizers`, one text per run, because in this export a padded batch changes the vectors. No torch. The model files are not in the repository (570 MB); `RAG_MODEL_DIR` (or the Hugging Face cache) says where they are, and the compose API service mounts them read-only. Without them search is full-text only and the response says `mode: "fts-only"`.
4. **Index:** schema `rag` (migration 0011): one table with German and English `tsvector` columns and a `vector(1024)` column with an HNSW cosine index. It is rebuilt from the committed corpus and vectors by `make seed` and `make rag-index`; it holds nothing the repository cannot rebuild.
5. **Retrieval, as evaluated:** full-text (OR of the words, German and English configurations) and vector search, 50 candidates each, reciprocal rank fusion with constant 60, top 5 (hybrid), and each method alone. Fixed before the evaluation (`agents/rag/EVAL_RULE.md`). **Served: vectors alone** (see point 8).
6. **CI without the model:** the chunk and question vectors are committed (`agents/rag/embeddings/`, about 1 MB) with a manifest of hashes. A test fails if the corpus text, the questions or the vectors change without `make rag-embed`, and the evaluation reads only the committed vectors. A test that needs the model (it must reproduce the committed vectors at cosine 0.999) is skipped where the model is absent.
7. **"No source found":** the best vector cosine below a threshold chosen on the dev questions only and frozen in `agents/rag/threshold.json`.
8. **Result and what it means.** On the 41 test questions vectors alone reach recall@5 of 100 %, full-text alone 49 %, and the hybrid 86 %: the pre-registered check that hybrid is at least as good as the better single method **failed**, mainly because half of the questions are English and the statute is German, so full-text adds noise that equal-weight fusion cannot discount. It was not tuned away. **Amendment (same phase, after review):** the first version of this ADR left the hybrid as the served method. That was wrong by the project's own convention (a challenger that fails its pre-registered check does not replace what did better). The setting `RAG_RETRIEVAL` (default `vector`) now serves vectors alone; `hybrid` and `fts` stay available. The choice was made after the results were known (the rule only said the failure is reported) and `rag.json` records that (`served.basis`). A test fails if the default and `rag.json` disagree. W13 shows the served method and the three results side by side. Follow-up: pre-register language-aware or weighted fusion and evaluate it on new questions before the hybrid can be served. Without the bge-m3 files every setting falls back to full-text only, visibly (`mode: "fts-only"`, `fallback: true`).

## Consequences

- The questions were written by the author of the corpus, and there are only eight without a source; the numbers describe this prototype, nothing wider.
- A first run embedded in padded batches; it was replaced after the defect was understood (the model card says so).
