# Retrieval fixtures (T3.2)

- `queries.jsonl` — labelled eval set (24 queries; ≥20 required by the gate).
  Each row: `query_id`, `record_id` (into `data/regulations/clauses.jsonl`),
  `query` (NL paraphrase or raw-code / confusion-probe form), `note`. The gold
  chunk for a query is the single chunk whose `(doc, clause_id)` matches the
  named clause record — T3.1 Gate A guarantees exactly one.
- `chunks.jsonl` — **frozen** chunker output used as the retrieval corpus (2361
  chunks over 8 versioned RBI docs, so old-version near-duplicates act as hard
  distractors). The 8th doc — the pre-2023-10 consolidation of the 2016 KYC MD,
  archived at T2.5 for P4/P5 old sides — joined the corpus here. Derived
  artifact; regenerate when the chunker changes:

  ```python
  from pathlib import Path
  from cobol_archaeologist.rag.chunker import build_all_chunks
  with Path("tests/fixtures/retrieval/chunks.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
      for c in build_all_chunks():
          fh.write(c.model_dump_json() + "\n")
  ```

The 4×3 mode comparison (bm25/dense/hybrid/hybrid_rerank × hit@1/hit@3/mrr@5) is
written to `docs/tasks/T3.2-relevance-report.md` by
`python -m cobol_archaeologist.rag.index` (Gate B — loads the pinned models, run
locally). The offline gates in `tests/test_retrieval.py` do not need it.
