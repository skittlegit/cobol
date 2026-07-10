# STATUS

One entry per task: ID, state, owner, and artifact.

- **T0.1** | done | B | `data/manifest.json` v1.1: CC Directions widening;
  CardDemo pinned at `59cc6c2`.
- **T0.2** | done | B | `docs/tasks/T0.2-taxonomy-examples.md` fit: card-conduct
  + KYC union. Anchor RE-ANCHORED at T2.1 (2026-07-09) to the 2025 Commercial
  Banks CC/DC Directions (2022 MD repealed 2025-11-28); KYC bridge is 2025 para
  90. See the T2.1 note.
- **T0.3** | done | C | `src/cobol_archaeologist/schemas.py` +
  `tests/test_schemas.py`. SCHEMA FROZEN — changes hereafter are CONTRACT
  CHANGEs (flag to A/B/C).
- **T0.4** | done | C | `docs/CONTRACT.md` v1.1 ACCEPTED — A, B, C signed
  2026-07-07. Amendments A1/A2 (tool_types.py normative) + B1-B3 folded in.
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
- **T1.4-T1.6** | todo | A | `docs/track-a-brief.md`. Unblocked by T1.3.
- **T2.1** | todo | B | Scope follows the T0.2 contract change. Re-verify CC
  amendments at curation.
- **T1.2-T1.6** | todo | A | `docs/track-a-brief.md`. Unblocked by T1.1.
- **T2.1** | done | B | `data/regulations/clauses.jsonl` (19 clauses,
  schema-gated by `tests/test_clauses.py`) anchored to the 2025 Commercial Banks
  CC/DC Directions + KYC 2025; 2025 para numbers secondary-mapped (primary pass
  at T2.5) + `docs/tasks/T2.1-clause-curation-note.md`.
- **T2.2-T2.4, T2.6** | todo | B | `docs/track-b-brief.md`. T2.2 is blocked on
  T1.4, T1.5, and T2.1.
- **T2.5** | todo | B | Phases 0–1: **6 of 7** primary RBI PDFs archived +
  sha256-pinned in `data/regulations/sources/MANIFEST.json` (gated by
  `tests/test_sources.py`) via `scripts/pin_regulations.py`. Gap:
  `kyc-amend-2023-10-17.pdf` `missing` — first download was the covering letter
  only; the amendment table is RBI's separate annexure (URL + fallback in that
  MANIFEST entry's `note`). Blocks Phase 2 encoding of P4's 15% old side only.
  Phases 2–4 remain: primary numbering/old-side pass [CHAT], then seed programs
  + ≥20 validated instances.
- **T3.1-T3.6** | todo | C | `docs/track-c-brief.md`. Stub-based, not blocked on
  Track A.
- **T4.x-T7.x** | todo | A/B/C | Per playbook Part 4; not yet in play.
