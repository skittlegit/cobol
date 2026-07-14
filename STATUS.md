# STATUS

One entry per task: ID, state, owner, and artifact.

- **T0.1** | done | B | `data/manifest.json` v1.1: CC Directions widening;
  CardDemo pinned at `59cc6c2`.
- **T0.2** | done | B | `docs/tasks/T0.2-taxonomy-examples.md` fit: card-conduct
  + KYC union. Anchor RE-ANCHORED at T2.1 (2026-07-09) to the 2025 Commercial
  Banks CC/DC Directions (2022 MD repealed 2025-11-28); KYC bridge is 2025 para
  90. See the T2.1 note.
- **T0.3** | done | C | `src/cobol_archaeologist/schemas.py` +
  `tests/test_schemas.py`. **SCHEMA v2 — RE-FROZEN 2026-07-12** per
  `docs/reviews/2026-07-12/contract-change-track-c-RESOLVED.md` (loci/
  SourceLineRef, recursive typed CurrentValue + comparator, target_path).
  Further changes are new CONTRACT CHANGEs (flag to A/B/C).
- **T0.4** | done | C | `docs/CONTRACT.md` v1.2. Amended by the 2026-07-12
  CONTRACT CHANGE; sign-offs stand.
- **T0.5** | done | A | `docs/tasks/T0.5-ast-decision-note.md`.
- **T0.6** | done | C | `docs/tasks/T0.6-novelty-note.md` — novelty sentence
  locked; cell 1-5 related-work skeleton for T7.5. Empty cell verified by live
  search 2026-07-07; key citations re-verified at landing.
- **T1.0** | done | A | `pyproject.toml` + `src/cobol_archaeologist/` skeleton +
  `vendor/tree-sitter-cobol/` (pinned `e99dbdc`) + `scripts/fetch_corpora.sh` +
  `tests/test_scaffold.py` (gate green on Python 3.12 / tree_sitter 0.21.3).
- **T1.1** | done | A | `src/cobol_archaeologist/ingest/cleaner.py` +
  `src/cobol_archaeologist/parser/{paragraphs,copybooks}.py` +
  `tests/test_{cleaner,copybooks,paragraphs}.py` + golden fixtures
  `tests/fixtures/paragraphs/*.json` (10 CardDemo programs, zero ERROR nodes,
  hand-verified nesting). New preprocessor rules (`NOT=` glued, continued
  literal splice) logged in `docs/preprocessor-notes.md`.
- **T1.2** | done | A | `src/cobol_archaeologist/static_analysis/call_graph.py`
  (`build_call_graph` → PERFORM/THRU/GO TO + cross-program CALL/LINK/XCTL edges,
  `unresolved`, `callers`/`callees`/`reachable_from`/`entry_points`) + D1
  taxonomy (`GOTO`/`CALL`/`dynamic` in `parser/paragraphs.py`, plus opt-in
  `include_preamble` for batch main-driver roots). Gate `tests/test_call_graph.py`
  + fixtures `tests/fixtures/call_graph/*.json` (5 programs, hand-verified) and
  `tests/fixtures/synthetic/DEADEX.cbl` (dead-code negative case).
- **T1.3** | done | A | `src/cobol_archaeologist/static_analysis/dataflow.py`
  (`trace_variable(var, programs, call_graph, program=None)` → AST-based def/use
  per the normative table; qualified/bare/ambiguous name resolution, REDEFINES-
  alias + 88→parent, VALUE-clause decl sites, LineMap-resolved copybook refs).
  Gate `tests/test_dataflow.py` + fixtures `tests/fixtures/dataflow/*.json`
  (10 variables over 4 programs, hand-verified).
- **T1.4** | done | A | `src/cobol_archaeologist/static_analysis/slicer.py`
  (`slice_on(var, programs, call_graph, program=None)` → backward slice over
  data + control dependence, VALUE-clause decls, interprocedural PERFORM/GO TO
  glue). Gate `tests/test_slicer.py` + fixtures `tests/fixtures/slices/*.json`
  (10 hand-verified slices). Fixed a latent T1.3 refmod/subref index
  over-extraction bug in `dataflow.py` (indices now untracked per the
  documented limitation; T1.3 gate stays green).
- **M1 (Slicing Validated): PASSED 2026-07-12 — slice_on matches 10 hand-built slices.**
- **T1.5** | done | A | `src/cobol_archaeologist/model/run_cobol.py`
  (`compile_check` syntax oracle → `CompileResult`; `run_cobol` /
  `run_cobol_with_files` sandboxed compile+execute → `RunResult`; temp-dir +
  5s timeout + minimal self-configuring env) + `scripts/setup_cobc.sh`. Gate
  `tests/test_run_cobol.py` (verified live on GnuCOBOL 3.2.0; skip-marked
  without `cobc`). CBACT04C is compile-only (JCL-called `PROCEDURE DIVISION
  USING` can't link as `-x`); full run on the trivial program.
- **T1.6** | done | A | `src/cobol_archaeologist/tools.py` (`RealToolLayer`:
  all 11 ToolLayer methods over T1.1–T1.5, parse-on-first-touch cache +
  one-shot call graph; `get_data_layout` is new logic — data-division field
  tree, VALUE text guaranteed original-source via LineMap) +
  `docs/tool-semantics.md` (consumer-facing sentinel/edge semantics) +
  `scripts/smoke_tools.py` + gate `tests/test_tools.py` (23 tests, incl.
  `isinstance(_, ToolLayer)`) + fixture `tests/fixtures/smoke/acct_curr_bal.json`.
  D0 review fixes landed with regression tests: F5 (`dataflow.py`
  case-insensitive qualified names), F6 (`cleaner.py` `PreprocessError` on
  unterminated EXEC/COPY at EOF), F10 (`fetch_corpora.sh` verifies CardDemo
  HEAD == pin).
- **Phase 1 (Track A) COMPLETE — tool layer live.**
- **T2.1** | done | B | `data/regulations/clauses.jsonl` (19 clauses,
  schema-gated by `tests/test_clauses.py`) anchored to the 2025 Commercial Banks
  CC/DC Directions + KYC 2025; 2025 para numbers primary-confirmed at T2.5 +
  `docs/tasks/T2.1-clause-curation-note.md`.
- **T2.2** | done | B | `src/cobol_archaeologist/benchmark/{mutate,surface}.py`
  + `tests/test_mutate.py` (**gates A–D green; 10 validated anchor instances
  across all operators; skips: 10 synthetic-locus records**).
- **T2.3-T2.4, T2.6** | todo | B | `docs/track-b-brief.md`.
- **T2.5** | done | B | `data/benchmark/seed/real_curated.jsonl` (**21
  instances, 5 T6 pairs, gates green**) + sources archive pinned.
- **T3.1** | done | C | `src/cobol_archaeologist/rag/{schemas,
  pdf_loader,chunker}.py` + `tests/test_chunker.py` + promoted 10-boundary
  golden fixture. Gates A (19/19 join), B (hand-checked anchor boundaries), and
  C green.
- **T3.2** | done | C | `src/cobol_archaeologist/rag/{index,embed}.py` +
  `tests/test_retrieval.py` + `docs/tasks/T3.2-relevance-report.md` +
  `tests/fixtures/retrieval/{queries,chunks}.jsonl`. Gates A/B/C green; bar
  met (hybrid_rerank mrr@5 0.744 > dense 0.592). Notable findings for T3.3
  and T5.5 recorded in T3.3 work order.
- **T3.3-T3.6** | todo | C | `docs/track-c-brief.md`. Stub-based, not blocked
  on Track A.
- **T4.x-T7.x** | todo | A/B/C | Per playbook Part 4; not yet in play.
