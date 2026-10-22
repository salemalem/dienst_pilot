# RAG evaluation rule (written before any retrieval was scored)

Committed before `eval/run_rag_eval.py` was run for the first time. `eval/results/rag.json`
records the SHA-256 of this file and of `eval/rag_questions.json`; a test fails if either changes
without the result being regenerated.

## What is evaluated

Retrieval over the corpus in `agents/rag/corpus/` (167 paragraph chunks: the ArbZG as published at
gesetze-im-internet.de and synthetic documents), with bge-m3 (ONNX, int8) vectors committed in
`agents/rag/embeddings/`. The questions are `eval/rag_questions.json`: 60 written for this
prototype, 30 German and 30 English, 52 answerable (any listed gold chunk answers it) and 8 with no
source in the corpus. They were written by the author of the corpus, which makes them easier than
questions from strangers; the report says so.

## Fixed settings (not tuned after seeing results)

- Hybrid retrieval: Postgres full-text (German and English configurations, OR of the question's
  words) and pgvector cosine, 50 candidates each, reciprocal rank fusion with constant 60,
  top 5 returned. The same settings are run as full-text only and vector only for comparison.
- Dev and test split by hash: a question is **dev** if the first byte of the SHA-256 of its id is
  below 86, otherwise **test**. The only thing chosen on dev questions is the "no source" threshold
  below; the test questions are scored once with that threshold frozen.

## "No source found"

A search says `found: false` when the best vector cosine of the question is below a threshold tau.
tau is chosen on the **dev** questions only, from the grid 0.30, 0.325, ... 0.70, as the value
that maximises balanced accuracy (the mean of the share of answerable questions kept and the
share of unanswerable questions rejected); ties go to the lower tau. It is then frozen into
`NO_SOURCE_COSINE` in the API and recorded in the result.

## Reported (test questions, tau frozen)

recall@1, @3, @5 over the answerable questions (a hit if any gold chunk is among the top k);
MRR; "citation correct at 1" (the top-ranked passage is a gold passage, so the citation the
copilot gives is one that answers the question); the same by question language; the share of
unanswerable questions correctly answered "no source" and the share of answerable questions
wrongly rejected; and the three modes side by side.

## What would count as a problem (stated now)

Hybrid recall@5 below 0.80 on the test questions, or hybrid not at least as good as the better of
the two single methods on recall@5, is reported as a failure of the retrieval design, not tuned
away. The status table says "Built & evaluated" for the rulebook only with these numbers beside it.
