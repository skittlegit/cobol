# STATUS

Authoritative task-state ledger. Each task has one entry with its state, owner,
artifact, and durable gate evidence.

## Completed milestones

Milestones are cross-task gates, not roadmap phases. Roadmap phases span all
three tracks; a task's numeric prefix does not identify its phase.

- **M0 (Spike & Decisions): COMPLETE** — parser bake-off and AST decision
  landed; T0.1–T0.6 are done.
- **M1 (Slicing Validated): PASSED 2026-07-12** — `slice_on` matches 10
  hand-built slices.
- **M2 (Synthetic v1 + Seed Started): PASSED 2026-07-17 — RE-EVIDENCED** — the
  594-row compiled catalogue, current Luna judge/drop evidence, 562-row accepted
  set, 21 real-curated seeds, and purpose-valid 583-row v1-pre splits are aligned.
  Track C may consume the corrected IDs and begin headline evaluation.
- **M3 (Agent Grounded): COMPLETE 2026-07-24** — T3.3b HyDE and T3.6 D1–D7
  policy hunts were independently reviewed and merged in PR #67; verified
  emission, D6 delegation, anti-shortcut policy, and the real/stub seam stand.

## Task ledger

- **T0.1** | done | B | `data/manifest.json` v1.1: CC Directions widening;
  CardDemo pinned at `59cc6c2`.
- **T0.2** | done | B | `docs/tasks/T0.2-work-order.md` fit: card-conduct
  + KYC union. Anchor RE-ANCHORED at T2.1 (2026-07-09) to the 2025 Commercial
  Banks CC/DC Directions (2022 MD repealed 2025-11-28); KYC bridge is 2025 para
  90. See the T2.1 work order.
- **T0.3** | done | C | `src/cobol_archaeologist/schemas.py` +
  `tests/test_schemas.py`. **SCHEMA v2 — RE-FROZEN 2026-07-12** per
  `docs/reviews/2026-07-12/contract-change-track-c-RESOLVED.md` (loci/
  SourceLineRef, recursive typed CurrentValue + comparator, target_path).
  Further changes are new CONTRACT CHANGEs (flag to A/B/C).
- **T0.4** | done | C | `docs/tasks/T0.4-work-order.md` +
  `docs/CONTRACT.md` v1.3. Ratified amendments and sign-offs stand.
- **T0.5** | done | A | `docs/tasks/T0.5-work-order.md`.
- **T0.6** | done | C | `docs/tasks/T0.6-work-order.md` — novelty sentence
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
  literal splice) recorded in `docs/tasks/T1.1-work-order.md`.
- **T1.2** | done | A | `src/cobol_archaeologist/static_analysis/call_graph.py`
  (`build_call_graph` → PERFORM/THRU/GO TO + cross-program CALL/LINK/XCTL edges,
  `unresolved`, `callers`/`callees`/`reachable_from`/`entry_points`) + D1
  taxonomy (`GOTO`/`CALL`/`dynamic` in `parser/paragraphs.py`, plus opt-in
  `include_preamble` for batch main-driver roots). The integrated reachability
  correction separates the single true `entry_points` root from
  `forest_roots`, traverses internal fall-through in `reachable_from`, and
  keeps fall-through out of caller/callee results. Gate
  `tests/test_call_graph.py` + hand-verified graph fixtures and synthetic
  `DEADEX.cbl`/`DEADISO.cbl`/`FALLTHRU.cbl` cases.
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
- **T1.5** | done | A | `src/cobol_archaeologist/model/run_cobol.py`
  (`compile_check` syntax oracle → `CompileResult`; `run_cobol` /
  `run_cobol_with_files` sandboxed compile+execute → `RunResult`; temp-dir +
  5s timeout + minimal self-configuring env) + `scripts/setup_cobc.sh`. Gate
  `tests/test_run_cobol.py` (verified on GnuCOBOL 3.2.0; BL-9 supports
  `>=3.1.2,<4`; skipped without `cobc`). CBACT04C is compile-only because its
  JCL-called `PROCEDURE DIVISION USING` cannot link as `-x`; full run on the
  trivial program.
- **T1.6** | done | A | `src/cobol_archaeologist/tools.py` (`RealToolLayer`:
  all 11 ToolLayer methods over T1.1–T1.5, parse-on-first-touch cache +
  one-shot call graph; `get_data_layout` is new logic — data-division field
  tree, VALUE text guaranteed original-source via LineMap) + the consumer
  semantics register in `docs/tasks/T1.6-work-order.md` +
  `scripts/smoke_tools.py` + gate `tests/test_tools.py` (23 tests, incl.
  `isinstance(_, ToolLayer)`) + fixture `tests/fixtures/smoke/acct_curr_bal.json`.
  D0 review fixes landed with regression tests: F5 (`dataflow.py`
  case-insensitive qualified names), F6 (`cleaner.py` `PreprocessError` on
  unterminated EXEC/COPY at EOF), F10 (`fetch_corpora.sh` verifies CardDemo
  HEAD == pin).
- **T2.1** | done | B | `data/regulations/clauses.jsonl` (19 clauses,
  schema-gated by `tests/test_clauses.py`) anchored to the 2025 Commercial Banks
  CC/DC Directions + KYC 2025; 2025 para numbers primary-confirmed at T2.5 +
  `docs/tasks/T2.1-work-order.md`.
- **T2.2** | done | B | `src/cobol_archaeologist/benchmark/{mutate,surface}.py`
  + `tests/test_mutate.py` (**gates A–D green; 10 validated anchor instances
  cover MO-0…MO-6 plus MO-1×/MO-3×/MO-6×; compiler gate verified with
  GnuCOBOL 3.2.0**) + `data/benchmark/probes/t2.2_surface_probe.jsonl` (100
  balanced records; AUC 0.50, bootstrap 95% CI [0.50, 0.50]).
- **T2.3** | done | B | Corrective catalogue at
  `data/benchmark/drift_instances.jsonl`: **594 compiled rows** with D1–D6
  distinct semantic counts **13/6/5/4/12/7**, zero class/operator/distinct
  shortfalls, and artifact-only Gate E **0.51765 [0.4382, 0.5952]**. The judged
  accepted artifact contains **562** synthetic rows. Manifest schema 2 carries
  BL-9 compiler provenance; the legacy catalogue banner is marked unavailable.
- **T2.4** | done | B | Current-catalogue `gpt-5.6-luna`/OpenAI/high evidence:
  canonical sample **50/50 plausible (100%, 0 unsure)**; full raw gate
  **557/594 (93.77%)**, passed. Five full-set `unsure` rows were human-accepted;
  final drop policy is **562 accepted / 32 implausible / 0 unsure**, override
  rate **5/594 (0.84%)**. The prescribed review agrees **15/15 (100%)**. See
  `data/benchmark/{judgements.sample50,judgements,human_review.sample15}.jsonl`.
- **T2.5** | done | B | `data/benchmark/seed/real_curated.jsonl` (**21
  instances, 5 intact verdict-flipping T6 pairs, zero degraded pairs, gates
  green**) + pinned primary-source archive.
- **T2.6** | done | B | Corrected `data/benchmark/v1-pre/` +
  `distribution.md`: train/dev/test = **297/106/180**, zero base overlap,
  train/dev synthetic shares = **52.8%/18.9%**, test-interprocedural = **36**
  (MO-1×/MO-3×/MO-6× = **12/8/12**), every D1–D7 test-local floor passes,
  D4/D5 interprocedural shortfalls are named, and **23** cells are CI-fragile.
- **T2.7** | ready | B | `docs/tasks/T2.7-work-order.md`: repair the 15
  source/provenance mismatches, expand real-curated T6 from 5 to at least 20
  intact pairs, regenerate/re-freeze v1-pre, and prove every test row
  materializes.
- **T3.1** | done | C | `src/cobol_archaeologist/rag/{schemas,
  pdf_loader,chunker}.py` + `tests/test_chunker.py` + promoted 10-boundary
  golden fixture. Gates A (19/19 join), B (hand-checked anchor boundaries), and
  C green; BL-13 nested-definition regression keeps KYC OVD `5(xiv)` distinct
  from the second definition group's Regulated Entities `(xiv)`.
- **T3.2** | done | C | `src/cobol_archaeologist/rag/{index,embed}.py` +
  `tests/test_retrieval.py` + the evidence block in
  `docs/tasks/T3.2-work-order.md`. Gate B table REFRESHED on the T2.5-expanded
  2,361-chunk/8-document fixture; bar held (`hybrid_rerank` mrr@5 0.744 >
  `dense` 0.588, ≥ on hit@1/hit@3). Findings vs the 7-doc run are in the work
  order's refresh section — note that the reranker is no longer a near-wash
  over `hybrid`; it is what absorbs the added distractors.
- **T3.3a** | done | C | `src/cobol_archaeologist/rag/search.py` + `tools.py`
  (search_regulations live) + `tests/test_search_regulations.py`. Reviewed
  2026-07-24; merged PR #61.
- **T3.3b** | done | C |
  `src/cobol_archaeologist/rag/hyde.py` +
  `tests/fixtures/retrieval/hyde_cache.json` + `tests/test_hyde.py`. Pinned-model
  24-query gate: dense mrr@5 0.588→0.722, hybrid-rerank 0.744→0.793; q23
  improves from absent in all modes to ranks 1/1/1/2. Reviewed and merged in
  PR #67.
- **T3.4** | done | C | `src/cobol_archaeologist/model/verify.py` +
  `tests/test_verify.py` + `tests/fixtures/verify/`. Reviewed 2026-07-24;
  16 gates green. The 55-row offline cache now uses the pinned DeBERTa neural
  backend. Verifier accuracy: 50 pairs generated, human labels pending in Track
  C chat (xfail until the complete label pass, then a hard gate).
- **T3.5** | done | C | `src/cobol_archaeologist/agent/{loop,stub_tools,
  trajectory}.py` + tests + golden late-fee trajectory. Reviewed 2026-07-24;
  17 gates green, seam purity + no-unverified-emission confirmed.
- **T3.6** | done | C | `src/cobol_archaeologist/agent/{policy.py,
  hunts/}` + `tests/test_policy_hunts.py`. Gates 1-8 green; D1-D7 registered,
  D6 delegates to verify.py reachability, anti-shortcut rule enforced.
  Reviewed and merged in PR #67; **M3 (Agent Grounded) complete.**
- **T4.1** | blocked-live-run | C |
  `src/cobol_archaeologist/eval/{schemas,materialize,run}.py` +
  `model/provider.py`. Week-7 mutation→real-tool→eval seam green; 165/180 test
  rows materialize, 15 fail closed on Track B base/provenance mismatch; live
  provider credentials absent.
- **T4.2** | ready-for-live-run | C |
  `src/cobol_archaeologist/eval/{metrics,statistics}.py`; frozen T1–T6 metrics
  and paired statistics implemented. Current T6 capacity is 5 pairs versus 20.
- **T4.3** | ready-for-live-run | C |
  `src/cobol_archaeologist/eval/trajectory.py`; replay/evidence/budget/shortcut
  assessment gates green.
- **T4.4** | ready-for-live-run | C |
  `src/cobol_archaeologist/eval/calibration.py`; coverage, abstention,
  attempted-unavailable tiers, calibration, and per-tier faithfulness green.
- **T4.5** | blocked-on-live-artifacts | C |
  `src/cobol_archaeologist/eval/{baselines,report}.py`; fail-closed M4 report
  implemented. Needs three paired live artifacts, 50 human verifier labels,
  and at least 20 T6 pairs.
- **T5.x-T7.x** | todo | A/B/C | Per playbook Part 4; not yet in play.
