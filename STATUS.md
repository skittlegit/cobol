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
- **T1.2-T1.6** | todo | A | `docs/track-a-brief.md`. Unblocked by T1.1.
- **T2.1** | done | B | `data/regulations/clauses.jsonl` (19 clauses,
  schema-gated by `tests/test_clauses.py`) anchored to the 2025 Commercial Banks
  CC/DC Directions + KYC 2025; 2025 para numbers secondary-mapped (primary pass
  at T2.5) + `docs/tasks/T2.1-clause-curation-note.md`.
- **T2.2-T2.4, T2.6** | todo | B | `docs/track-b-brief.md`. T2.2 is blocked on
  T1.4, T1.5, and T2.1.
- **T2.5** | todo | B | UNBLOCKED (T0.3✓ + T2.1✓). Work list = T6 pair registry
  in `docs/tasks/T2.1-clause-curation-note.md`; first archive primary PDFs into
  `data/regulations/sources/` (sha256 pins) — including the 2025 CC Directions to
  confirm the secondary-mapped para 1–97 numbering — then resolve PROVISIONAL KYC
  clause_ids and encode old-side pair texts.
- **T3.1-T3.6** | todo | C | `docs/track-c-brief.md`. Stub-based, not blocked on
  Track A.
- **T4.x-T7.x** | todo | A/B/C | Per playbook Part 4; not yet in play.
