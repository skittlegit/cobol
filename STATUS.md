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
- **M3 (Agent Grounded): COMPLETE 2026-07-24** — T3.3 HyDE and T3.6 D1–D7
  policy hunts were independently reviewed and merged in PR #67; verified
  emission, D6 delegation, anti-shortcut policy, and the real/stub seam stand.
- **M4 (Narrow End-to-End): CLOSED — NO_GO 2026-07-26** — all three canonical
  Luna-Codex systems completed 204/204 frozen rows at commit `357f483` with
  valid, paired, zero-infrastructure artifacts. The frozen report is evaluable
  with zero blocking issues: agent T1 F1 0.3665, interprocedural delta versus
  dense-RAG -0.3030 (95% CI [-0.4929, -0.1252], p=0.00635), and T6 2/20.
  This valid NO_GO closes the Week-10 checkpoint.
  **Established:** the agent trails dense-RAG interprocedurally; the CI
  excludes zero and the predeclared GO bars fail.
  **NOT established:** the oracle-slice deconfounder is INCONCLUSIVE — delta
  -0.1964, 95% CI [-0.4330, +0.0348], crossing zero. The T4.5 reframing rule
  triggers on the agent failing to beat oracle-slice; that comparison did not
  resolve, so the rule has NOT fired. A slicer-first framing is an open
  option, not a finding, and must not be adopted by default.
  Decision, diagnosis, config-2 record, and final corrective work:
  `docs/tasks/T4.5-work-order.md`.

## Task ledger

- **T0.1** | done | B | `data/manifest.json` v1.1: CC Directions widening;
  CardDemo pinned at `59cc6c2`.
- **T0.2** | done | B | `docs/tasks/T0.2-work-order.md` fit: card-conduct
  + KYC union. Anchor RE-ANCHORED at T2.1 (2026-07-09) to the 2025 Commercial
  Banks CC/DC Directions (2022 MD repealed 2025-11-28); KYC bridge is 2025 para
  90. See the T2.1 work order.
- **T0.3** | ready-for-review | C | Schema v3 adds `DriftPrediction`;
  `DriftInstance` gold remains unchanged. CONTRACT v1.4 makes provenance and
  `gold_rationale` gold-only. Provider repair, full seven-hunt replay, and paid
  run guards are offline-gated; no provider spend.
- **T0.4** | done | C | `docs/tasks/T0.4-work-order.md` +
  `docs/CONTRACT.md` v1.4. Ratified amendments and sign-offs stand.
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
  The obsolete `search_regulations` stub assertion is retired; its gate now
  pins offline delegation and typed-list semantics for Track C's live service.
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
- **T2.7** | done | B | Phase-2 M4 inputs repaired: **204/204** test rows
  materialize, the real-curated seed has **51 rows / 20 intact T6 pairs**, and
  v1-pre is re-frozen at **307/102/204**. SHA-256 train/dev/test =
  `4b333851b97629083bfb753cbed28a0c47a5cbe5376d270731b7eb47ab982763` /
  `31842be32741d00c970e4d1f50d9a38e22774e3455cb9300922bc642a1b0ffef` /
  `5e8fb3676aab8ff2f886d72c6faab2c1a4b60f2595a3374eaa400e35f3d31d58`.
  All T2.5/T2.6/T2.7 gates pass; 41 seed bases and eight materialized
  replacements compile under **GnuCOBOL 3.2.0**.
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
- **T3.3** | done | C | Part A:
  `src/cobol_archaeologist/rag/search.py` + `tools.py`
  (`search_regulations` live) + `tests/test_search_regulations.py`, merged in
  PR #61. Part B: `src/cobol_archaeologist/rag/hyde.py` +
  `tests/fixtures/retrieval/hyde_cache.json` + `tests/test_hyde.py`.
  Pinned-model 24-query gate: dense mrr@5 0.588→0.722, hybrid-rerank
  0.744→0.793; q23 improves from absent in all modes to ranks 1/1/1/2.
  Both parts reviewed; final merge PR #67.
- **T3.4** | done | C | `src/cobol_archaeologist/model/verify.py` +
  `tests/test_verify.py` + `tests/fixtures/verify/`. Reviewed 2026-07-24;
  16 gates green. The 55-row offline cache now uses the pinned DeBERTa neural
  backend. All 50 independently supplied labels are recorded: 49/50 correct
  (98.0%), 21 TP, 28 TN, 1 FP (`acc_neg_04`), 0 FN; false-accept rate
  1/29 = 3.45%, below the frozen 10% ceiling. The accuracy gate is now hard
  green (`17 passed, 1 skipped`; GnuCOBOL unavailable locally).
- **T3.5** | done | C | `src/cobol_archaeologist/agent/{loop,stub_tools,
  trajectory}.py` + tests + golden late-fee trajectory. Reviewed 2026-07-24;
  17 gates green, seam purity + no-unverified-emission confirmed.
- **T3.6** | done | C | Approved with 17 gates green. Registered D1–D7 hunts
  retain all trajectories, prohibit edit-artifact shortcuts, require positive
  D7 evidence, and delegate D6 reachability to the T3.4 verifier. M3 closed.
- **T4.1** | done | C | Canonical ChatGPT-authenticated Codex
  `gpt-5.6-luna`/high artifacts at `357f483`: agent, dense-RAG, and
  oracle-slice each 204/204, exact frozen order, manifest/run-key matched,
  `VALID`, zero infrastructure and contract failures. Agent retained 47
  verified predictions and 4,570 successful tool observations (mean 22.40);
  no unverified emission exists. One timed-out operational shard attempt is
  preserved outside the canonical artifact; its unchanged 68-row retry was
  clean.
- **T4.2** | done | C | Frozen 10,000-resample scoring completed. T1 F1:
  agent 0.3665, dense-RAG 0.7279, oracle-slice 0.5714. Agent T6 is evaluable at
  2/20 (0.1000), exact 95% CI [0.0123, 0.3170].
- **T4.3** | done | C | 204 trajectory assessments persisted: 204 replayable,
  204 shortcut-free, 190 budget-consistent, 47 complete selected evidence
  paths, and 20 gold-typed grounded code facts.
- **T4.4** | done | C | Agent coverage 47/204 (0.2304), answered accuracy
  0.8936, aggregate faithfulness 0.4255; Tier 1/2/3 faithfulness =
  0.1667/0.7200/0.0625. Brier 0.1816, ECE 0.1713.
- **T4.5** | M4 done — NO_GO; config-2 final amendment implemented, fresh smoke pending | C |
  `data/eval/m4/report.{json,md}` has zero blocking issues. Agent trails
  dense-RAG interprocedurally by 0.3030 (95% CI [-0.4929, -0.1252],
  p=0.00635); the oracle-slice comparison is inconclusive because its CI
  crosses zero. M4 remains closed and the framing is benchmark-first.
  Integrated diagnosis in `docs/tasks/T4.5-work-order.md`: F1 cleared Track A
  after 47/49 program filenames were misbound as copybooks; F2 found the
  interprocedural gap coverage-driven. X1/X1b/X2/X3′/X4 landed at `7cc1740`
  with 439 passed, 71 skipped, 5 deselected and Ruff clean. The first
  config-2 smoke at `0e3c1d0` completed 5/5 with no infrastructure/contract
  failures but zero predictions; its first-N sample contained three D7 null-
  value rows although only 8/204 split rows have null values. Final corrective
  phase X5–X7 is now implemented: seed `20260726` reproducibly pins one row
  per D1–D7 class and persists all seven IDs before execution; value
  requirements are scoped to D1/D4/D5; and a first-turn finding is re-prompted
  until one successful bounded observation exists. Offline gates are **448
  passed, 71 skipped, 5 deselected**, with Ruff clean. No provider run was
  performed in the implementation commit. The representative config-2 smoke
  and, if valid, the paired run remain pending under the binding hard stop in
  the canonical T4.5 work order. Final Amendment 3 keeps X3′ and the verifier
  unchanged, requires source-exact static-claim tokens, and fails malformed
  hooks closed before verification without rewriting or re-prompting.
  The pre-amendment 0/7 evidence is archived at
  `data/eval/m4-config2/smoke-pre-amendment-e6a7762/`. Implementation gates:
  **450 passed, 71 skipped, 5 deselected**, Ruff clean, verifier SHA-256
  `698eb8e…c019d17`. No provider spend occurred in the implementation commit;
  M4 remains closed as NO_GO.
- **T5.x-T7.x** | todo | A/B/C | Per playbook Part 4; not yet in play.
