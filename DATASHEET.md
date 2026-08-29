# Datasheet — COBOL Archaeologist Benchmark v1

Follows the spirit of Gebru et al.'s "Datasheets for Datasets." This
document is the canonical, reviewer-auditable description of
`data/benchmark/v1/`. It is written to make composition, provenance,
leakage controls, limitations, and intended use checkable without access
to chat history — everything it states is either a computed statistic over
the frozen files or a pointer to the work order that decided it.

## Motivation

The benchmark measures whether a system can detect where legacy COBOL
banking code has drifted from the financial regulation it was built to
satisfy — stale thresholds, missing checks, contradictions, stale
reference data, boundary errors, and dead compliance code — with a
verified, evidence-linked explanation. It exists because the drift-
detection *task* has no public benchmark: general code-QA or vulnerability
benchmarks do not test whether a claimed compliance judgment is actually
grounded in both the cited regulation clause and the cited source
coordinates. See `CLAUDE.md` for the full project framing and
`docs/tasks/T0.2-work-order.md` for the D1–D7 taxonomy this benchmark
implements.

## Composition

One row is one `DriftInstance`: a temporally-pinned regulation clause, one
or more original-source code loci, exactly one class (D1–D7), program/
paragraph/line labels, and a gold rationale. `data/benchmark/v1/` freezes
three splits:

| split | rows | source | interprocedural |
|---|---|---|---|
| train | 307 | 307 synthetic | 7 |
| dev   | 102 | 102 synthetic | 0 |
| test  | 196 | 153 synthetic + **43 real-curated** | 36 |

Class distribution (`D1_stale_threshold` … `D7_conformant`):

| split | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
|---|---|---|---|---|---|---|---|
| train | 54 | 32 | 26 | 2 | 67 | 23 | 103 |
| dev | 29 | 8 | 15 | 4 | 17 | 0 | 29 |
| test | 61 | 14 | 23 | 14 | 18 | 23 | 43 |

Test contains **9 intact verdict-flipping T6 pairs** (byte-identical
`code_locus` evaluated against two clause versions with opposite
conformance verdicts) — see **Limitations** for why this is below the
original 20-pair target. Base-program groups never cross splits (T2.6/T2.7
gate, re-verified at freeze).

Synthetic rows are the accepted T2.3/T2.4 catalogue: mutation-generated
drift instances over the AWS CardDemo corpus (Apache-2.0, pinned commit
`59cc6c2fd7eb`), filtered through a compile/behavior oracle and an
independent LLM-judge plausibility pass (557/594 raw-gate pass, 562
accepted after human-reviewed overrides — `docs/tasks/T2.4-work-order.md`).
Real-curated rows are hand-authored small COBOL programs plus three real
CardDemo programs (`CBTRN02C`, `CBACT04C`), each citing a primary RBI
regulation clause (RBI Commercial Banks CC/DC Directions 2025, its
repealed 2022 predecessor, and the RBI KYC Directions 2016/2025) —
`data/manifest.json` is the canonical anchor-regulation record.

## Collection / generation process

1. **Anchor regulations** (T0.1/T0.2, re-anchored T2.1): RBI Commercial
   Banks CC/DC Directions 2025 (effective 2025-11-28) plus the KYC
   Directions 2025 it incorporates by reference at paragraph 90; the
   repealed 2022 Master Direction supplies old-side T6 pairs.
2. **Synthetic generation** (T2.2–T2.4): a mutation operator library
   (`src/cobol_archaeologist/benchmark/mutate.py`) applies MO-0 (benign,
   non-drift) through MO-6 (plus interprocedural MO-1×/MO-3×/MO-6×
   variants) to CardDemo-derived and repo-native GnuCOBOL bases, gated by
   a compile/behavior oracle (GnuCOBOL 3.2.0, BL-9 policy
   `>=3.1.2,<4`) and an independent-model-family plausibility judge.
3. **Real-curated seed and scale-up** (T2.5/T2.7/T5.1): 51 candidates —
   hand-authored COBOL evaluated against pinned primary regulation text,
   including 20 candidate T6 pairs (10 clause families) constructed to
   test verdict-flipping across the 2016/2022→2025 clause transitions.
4. **Splitting** (T2.6/T2.7): deterministic, group-preserving assignment
   (`src/cobol_archaeologist/benchmark/splits.py`, seed `2600`) enforces
   zero base-program overlap across splits, reserves all real-curated rows
   to test, and repairs purpose-level minima (per-class floors, CI-fragile
   cell flags) without moving a base group across a split boundary.
5. **Freeze** (T5.2): `src/cobol_archaeologist/benchmark/freeze.py`
   replaces the 51 placeholder real-curated test rows with the T5.1-
   adjudicated final instances, hashes every split, and writes
   `data/benchmark/v1/manifest.json`. No row moves between splits after
   this point.

## Annotation and agreement

Full protocol: `ANNOTATION.md`. A human performed the primary annotation
of each of the 51 real-curated candidates, and Claude then performed a
separate verification pass over the same evidence bundle (pinned clause +
source, with existing gold, provenance, and mutation metadata withheld).
Agreement was computed before human final review:

- inclusion agreement: raw 94.1%, Cohen's κ 0.807 (bootstrap 95% CI
  [0.86, 1.00])
- class agreement (40 comparable rows): raw 95.0%, κ 0.927, Krippendorff's
  α 0.928

13 candidates required final review (7 both-passes-convergent
`needs_adjudication` citing ANNOTATION.md's own P1 day-basis-ambiguity
rule, 5 genuine cross-pass disagreements, 1 upstream-evidence gap). Every
one carries an immutable record in
`data/benchmark/annotation/adjudication_log.jsonl` (candidate ID, both
original readings, final human outcome, reviewer, evidence pointer,
rationale). **8 candidates were excluded** rather than forced to an
under-evidenced label — see Limitations.

The frozen records identify these roles explicitly as `Human-Primary`,
`Claude-Verification`, and `Human-Final-Review`. The agreement statistics
measure concordance between the human annotation and Claude verification;
they are not presented as inter-human agreement.

## Preprocessing

All COBOL source is run through the mandatory, line-count-preserving
preprocessor (`src/cobol_archaeologist/ingest/cleaner.py`) before parsing:
`EXEC CICS/SQL/DLI … END-EXEC` blocks are masked (preserving a sentence-
terminating period), and `COPY … REPLACING` is expanded. Every `SourceLocus`
and `SourceLineRef` in this benchmark refers to **original source line
numbers**, never post-transformation coordinates — this is a frozen
project invariant (`CLAUDE.md` §3).

## Leakage controls

- Gold-only fields (`gold_rationale`, `provenance`, mutation operator
  names/diffs, generator seeds, judge verdicts, prior labels) are never
  present in any system-visible input; `DriftPrediction` (the detector-
  facing schema) structurally cannot carry them.
- MO-0 benign, non-drift-producing edits are mixed into the mutation
  corpus so edit-artifact style alone cannot predict drift.
- The `literal_roundness` probe and the registered six-feature
  attacker-with-bases surface probe (`t2.2_surface_probe.jsonl`, AUC 0.50,
  bootstrap 95% CI [0.50, 0.50]) are declared **evaluation controls**, not
  annotation shortcuts — annotators are explicitly instructed not to use
  git history, mtimes, formatting discontinuities, or comment freshness as
  evidence (`ANNOTATION.md` §Anti-gaming).
- The six-feature probe is exactly balanced per feature: each feature has the
  same sorted value multiset in its 50 drift and 50 MO-0 rows, so every
  per-feature AUC is 0.5. The registered attacker consequently fits six zero
  weights and zero bias and collapses to an all-drift prevalence predictor.
  Its F1 0.8768 is retained as **null anti-gaming evidence**, not evidence of a
  strong attacker. T5.3's old +0.10 agent-over-attacker floor is **VACATED**
  and is not an M5 pass/fail requirement.
- Base-program groups never cross train/dev/test.

## Recommended metrics

- Primary: per-class F1 with exact/Wilson confidence intervals, stratified
  by `is_interprocedural`.
- T6 paired accuracy on the 9 intact verdict-flipping pairs — report the
  exact binomial interval; note that `len(pairs) >= 20` (this repo's own
  `reporting_bar_evaluable` convention in
  `src/cobol_archaeologist/eval/metrics.py`) is **not met** at 9 pairs, so
  paired-accuracy claims from this freeze are directional, not a headline
  bar-clearing result.
- Faithfulness/verification tier (1 executed / 2 static / 3 entailment-
  only) should always be reported alongside raw accuracy — see T4.4's
  Tier 1/2/3 faithfulness breakdown for the established methodology.

## Frozen M5 evaluation findings and use constraints

T5.4 evaluated nine systems on the same 196 ordered v1 test IDs with zero
unresolved infrastructure failures. The canonical report is
`data/eval/m5/report.{json,md}`; T5.5's deterministic audit and interpretation
are `data/eval/m5/benchmark-first-analysis.{json,md}`.

The headline result is negative and statistically supported. On all 36
interprocedural rows, the frozen agent has T1 F1 0.4000 versus 0.6939 for
RAG+reranker: delta -0.2939, paired bootstrap 95% CI
[-0.4990, -0.1101], paired-randomization p=0.01175. The agent therefore
significantly underperforms the strongest frozen non-agentic model baseline on
this stratum. This must not be softened to "inconclusive."

Coverage is central to that result. The agent answered 42/196 rows (0.2143)
and abstained on 154/196 (0.7857), with full-coverage F1 0.3665. Its answered-
subset accuracy must never be quoted without answer rate and full-coverage
performance. Frozen error analysis records 93 coverage/abstention failures,
61 insufficient-evidence outcomes, 25 evidence-verification failures, 22
localization failures among 42 answered rows, and failures on 31/36
interprocedural rows; categories overlap and do not by themselves establish a
single causal mechanism.

T6 is 1/9 (0.1111), exact 95% CI [0.0028, 0.4825]. It remains
`NOT_EVALUABLE_FOR_BAR` because the declared minimum is 20 pairs. It is
directional evidence only and cannot support a formal temporal-bar claim.

M4 remains a valid `NO_GO`; the larger Phase-5 analysis does not retroactively
reinterpret it. The benchmark contribution and detector result must be kept
separate: v1 establishes a frozen, provenance-auditable, version-conditioned
evaluation with leakage controls and reproducible stratified measurements.
The current agent does not solve it. Poor detector performance alone proves
neither benchmark novelty nor practical utility.

Provider-backed findings are specific to ChatGPT-authenticated
`gpt-5.6-luna` and the recorded prompts, budgets, and verifier. Agent,
RAG+reranker, and oracle-slice artifacts combine source-identical M4 reuse with
targeted Phase-5 reruns; they are descriptive paired comparisons, not
controlled prompt or reasoning-effort ablations. Tokens and tool calls are
reported from frozen trajectories, but no dollar cost is estimated because no
metered billing record exists.

## Limitations

- **43/51, not 51/51, real-curated test rows.** 8 candidates were excluded
  by adjudication rather than forced to a label: 7 because the 2022-clause
  text is genuinely silent on calendar-vs-working-day penalty accrual
  (ANNOTATION.md's own documented P1 rule) and no decisive primary
  authority was found; 1 because neither annotation pass nor adjudication
  could establish from available evidence whether a particular program's
  behavior actually implements the cited filing obligation. Full list in
  `data/benchmark/v1/manifest.json`'s `excluded_candidate_ids`.
- **9, not 20, intact T6 pairs.** Five T6CL pairs lost their old (2022)
  side to the P1 exclusion above; one T6KYC pair lost one side to the
  clause-scope exclusion. T6 paired-accuracy claims on this freeze have a
  small denominator (exact binomial CI will be wide) and do not meet this
  project's own 20-pair reporting-bar convention.
- **D4 is thin outside test** (2 train, 4 dev) and **D6 is absent from
  dev** — both are flagged CI-fragile per T2.6/T2.7's own distribution
  reporting; do not read a near-zero dev score on these classes as a
  reliable per-class signal.
- **This benchmark does not establish that any detector performs well.**
  M4 (`STATUS.md`) closed **NO_GO 2026-07-26**: on this benchmark's
  predecessor split, the evaluated agent trailed dense-RAG interprocedurally
  by 0.3030 F1 (95% CI [-0.4929, -0.1252], p=0.00635), and the
  oracle-slice comparison was inconclusive (CI crosses zero). A hard
  benchmark is not evidence that any particular detection method is close
  to solving the task, and conversely a method's poor score on this
  benchmark should not be read as proof the benchmark itself is
  miscalibrated — both readings require separate evidence.
- **Scope and external validity are limited.** Only 43 test rows are
  real-curated, regulatory coverage is confined to selected RBI card/debit-card
  and KYC/AML clauses and versions, and COBOL coverage is dominated by
  CardDemo-derived and repository-native programs. Systems consume
  reconstructed/materialized source bundles rather than an unrestricted
  production mainframe environment.
- **Class/locus cells are sparse.** D2, D3, D4, D5, and D7 have fewer than ten
  interprocedural rows. T5.4 marks these cells CI-fragile; their point estimates
  are not broad class-level findings.
- **The test distribution is drift-heavy.** There are 153 drift rows and 43
  conformant rows. All-drift predictors therefore obtain F1 0.8768 while
  balanced accuracy remains 0.5; raw F1 must be interpreted with prevalence
  and balanced accuracy.
- **Canonical hash governance is reconciled.** Phase-5 and the Track B-owned v1
  manifest use canonical LF split identities. The test identity is
  `bc9e775a727d82c7d5a30fd0495512bffde173bec2580e3d08664b8d98b2aed4`;
  the metadata repair did not change benchmark content.

## Licensing

- AWS CardDemo: Apache License 2.0, pinned commit `59cc6c2fd7eb`
  (`data/manifest.json`).
- IBM CICS Bank Sample Application (secondary corpus, not consumed by this
  v1 freeze): EPL-2.0.
- Repo-native GnuCOBOL seed bases (`data/benchmark/seed/programs/**`):
  authored within this repository, no external license applies.
- RBI regulation text: publicly issued Indian financial-sector regulation
  (RBI Commercial Banks CC/DC Directions 2025, RBI KYC Directions
  2016/2025, and the repealed 2022 Master Direction), archived with SHA-256
  pins at `data/regulations/sources/MANIFEST.json`. Quoted for compliance-
  research and citation purposes; consult the original RBI publication for
  authoritative legal text.
- Annotation guidelines, mutation operators, and all project code: governed
  by this repository's own license.

## Maintenance

`data/benchmark/v1/` is immutable once frozen — no row moves between
splits or changes value after `manifest.json` is written
(`docs/tasks/T5.2-work-order.md`). A future correction (for example,
resolving one of the 8 excluded candidates with new primary evidence) is a
new versioned freeze (`v2`, etc.), not an in-place edit. `manifest.json` records
`schema_version`, per-split SHA-256 hashes, the annotation-evidence SHA-256
set (both passes, final-review log, resolved real rows), and
`detector_visible_changes`. All 43 surviving real-curated rows have refined
code-locus/oracle inputs relative to `v1-pre`; `drift_000021` also expands the
materialized source bundle. Consequently, oracle-slice must rerun the 43 real
rows and source-based agent/RAG+reranker systems must rerun `drift_000021`;
reuse of other rows remains subject to the T5.4 identity gates.
