# T5.5 Benchmark-First Analysis and M5 Decision — COMPLETE

## Decision

M5 is **CLOSED** on frozen evidence. This records the measured negative detector result; it does not require an agent GO and does not activate M8.

## Validity audit

| Gate | Result |
|---|---|
| t5.4_report_reproduces_exactly | PASS |
| t5.4_error_analysis_reproduces_exactly | PASS |
| required_systems_present | PASS |
| all_systems_have_196_ordered_ids | PASS |
| canonical_lf_benchmark_identity | PASS |
| artifact_hashes_recorded | PASS |
| zero_unresolved_infrastructure_failures | PASS |
| reuse_rerun_provenance_present | PASS |
| human_annotation_provenance_present | PASS |
| excluded_ids_absent | PASS |
| t5.3_surface_floor_vacated | PASS |
| t5.4_negative_headline_preserved | PASS |
| m4_no_go_preserved | PASS |
| t6_minimum_not_met | PASS |
| no_provider_runs | PASS |

Canonical benchmark: 196 rows, SHA-256 `bc9e775a727d82c7d5a30fd0495512bffde173bec2580e3d08664b8d98b2aed4`, with all eight excluded candidate IDs absent.

The stale Track B CRLF hashes remain a cross-track issue; this analysis uses the ratified canonical LF identity and does not edit Track B's manifest.

## M4 result of record

M4 was a valid, evaluable NO_GO under its frozen bars. Phase-5 scale and new baselines do not retroactively alter that result.

## Frozen T5.4 headline

On all 36 paired interprocedural rows, agent F1 0.4000 versus RAG+reranker 0.6939; delta F1 -0.2939, paired bootstrap 95% CI [-0.4990, -0.1101], paired randomization p=0.0117.

The agent significantly underperforms the strongest frozen non-agentic model baseline on this stratum. This is not inconclusive, and detector failure alone does not prove benchmark novelty or utility.

## Benchmark contribution versus detector finding

The benchmark contribution establishes:

- a frozen version-conditioned COBOL regulatory-drift task with 196 aligned test rows.
- reviewer-auditable provenance, exclusions, leakage controls, and evidence-linked labels.
- reproducible full-coverage, locus, class, temporal-pair, faithfulness, calibration, and paired-comparison measurements.
- null evidence that the six registered surface features do not distinguish the balanced T2.2 probe.

It does not establish:

- practical utility in production mainframe compliance workflows.
- detector superiority or that the current agent solves the task.
- novelty merely because evaluated systems perform poorly.
- a formal T6 bar result from nine pairs.

The frozen agent significantly underperforms RAG+reranker on interprocedural T1 F1 and has low full-coverage performance.

The agent answered 42/196 and abstained on 154/196. Its 0.9048 answered accuracy must not be reported without the 0.2143 answer rate and full-coverage F1 0.3665.

Frozen trajectories categorize 93 agent outcomes as coverage/abstention failures and 61 as insufficient evidence; 25 rows have evidence-verification failures, 22/42 answered rows have localization failures, and 31/36 interprocedural rows fail. These categories may overlap and do not license unsupported causal claims.

## Frozen T1 comparisons

| System | Overall F1 | Local F1 | Interprocedural F1 | Answer rate | Abstentions |
|---|---:|---:|---:|---:|---:|
| agent | 0.3665 | 0.3576 | 0.4000 | 0.2143 | 154 |
| plain_llm | 0.7023 | 0.7324 | 0.5714 | 0.5561 | 87 |
| rag_dense | 0.7259 | 0.7642 | 0.5532 | 0.5408 | 90 |
| rag_reranker | 0.7410 | 0.7511 | 0.6939 | 0.6378 | 71 |
| oracle_slice | 0.6024 | 0.6305 | 0.4783 | 0.4898 | 100 |
| train_majority | 0.8768 | 0.8612 | 0.9412 | 1.0000 | 0 |
| prevalence_random | 0.7331 | 0.7085 | 0.8276 | 1.0000 | 0 |
| static_keyword | 0.7040 | 0.6120 | 0.9552 | 1.0000 | 0 |
| attacker_with_bases | 0.8768 | 0.8612 | 0.9412 | 1.0000 | 0 |

## D1–D7 full-coverage strata

| System | Class | n | Local | Interprocedural | T1 F1 | Answer rate |
|---|---|---:|---:|---:|---:|---:|
| agent | D1_stale_threshold | 61 | 49 | 12 | 0.2817 | 0.1803 |
| agent | D2_missing_rule | 14 | 14 | 0 | 0.3529 | 0.2143 |
| agent | D3_contradictory | 23 | 15 | 8 | 0.1600 | 0.0870 |
| agent | D4_stale_reference_data | 14 | 14 | 0 | 0.6667 | 0.5000 |
| agent | D5_boundary_error | 18 | 18 | 0 | 0.7143 | 0.5556 |
| agent | D6_dead_code | 23 | 11 | 12 | 0.2308 | 0.1304 |
| agent | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.1395 |
| plain_llm | D1_stale_threshold | 61 | 49 | 12 | 0.8598 | 0.7541 |
| plain_llm | D2_missing_rule | 14 | 14 | 0 | 0.5263 | 0.3571 |
| plain_llm | D3_contradictory | 23 | 15 | 8 | 0.8780 | 0.7826 |
| plain_llm | D4_stale_reference_data | 14 | 14 | 0 | 0.4444 | 0.2857 |
| plain_llm | D5_boundary_error | 18 | 18 | 0 | 0.8000 | 0.6667 |
| plain_llm | D6_dead_code | 23 | 11 | 12 | 0.4667 | 0.3043 |
| plain_llm | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.3953 |
| rag_dense | D1_stale_threshold | 61 | 49 | 12 | 0.8704 | 0.7705 |
| rag_dense | D2_missing_rule | 14 | 14 | 0 | 0.7826 | 0.6429 |
| rag_dense | D3_contradictory | 23 | 15 | 8 | 0.8500 | 0.7391 |
| rag_dense | D4_stale_reference_data | 14 | 14 | 0 | 0.4444 | 0.2857 |
| rag_dense | D5_boundary_error | 18 | 18 | 0 | 0.8750 | 0.7778 |
| rag_dense | D6_dead_code | 23 | 11 | 12 | 0.2308 | 0.1304 |
| rag_dense | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.2791 |
| rag_reranker | D1_stale_threshold | 61 | 49 | 12 | 0.9298 | 0.8689 |
| rag_reranker | D2_missing_rule | 14 | 14 | 0 | 0.5263 | 0.3571 |
| rag_reranker | D3_contradictory | 23 | 15 | 8 | 0.8500 | 0.7391 |
| rag_reranker | D4_stale_reference_data | 14 | 14 | 0 | 0.4444 | 0.2857 |
| rag_reranker | D5_boundary_error | 18 | 18 | 0 | 1.0000 | 1.0000 |
| rag_reranker | D6_dead_code | 23 | 11 | 12 | 0.4138 | 0.2609 |
| rag_reranker | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.5116 |
| oracle_slice | D1_stale_threshold | 61 | 49 | 12 | 0.7158 | 0.5574 |
| oracle_slice | D2_missing_rule | 14 | 14 | 0 | 0.7826 | 0.6429 |
| oracle_slice | D3_contradictory | 23 | 15 | 8 | 0.8780 | 0.7826 |
| oracle_slice | D4_stale_reference_data | 14 | 14 | 0 | 0.4444 | 0.2857 |
| oracle_slice | D5_boundary_error | 18 | 18 | 0 | 0.5000 | 0.3333 |
| oracle_slice | D6_dead_code | 23 | 11 | 12 | 0.2963 | 0.1739 |
| oracle_slice | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.4884 |
| train_majority | D1_stale_threshold | 61 | 49 | 12 | 1.0000 | 1.0000 |
| train_majority | D2_missing_rule | 14 | 14 | 0 | 1.0000 | 1.0000 |
| train_majority | D3_contradictory | 23 | 15 | 8 | 1.0000 | 1.0000 |
| train_majority | D4_stale_reference_data | 14 | 14 | 0 | 1.0000 | 1.0000 |
| train_majority | D5_boundary_error | 18 | 18 | 0 | 1.0000 | 1.0000 |
| train_majority | D6_dead_code | 23 | 11 | 12 | 1.0000 | 1.0000 |
| train_majority | D7_conformant | 43 | 39 | 4 | 0.0000 | 1.0000 |
| prevalence_random | D1_stale_threshold | 61 | 49 | 12 | 0.7921 | 1.0000 |
| prevalence_random | D2_missing_rule | 14 | 14 | 0 | 0.8800 | 1.0000 |
| prevalence_random | D3_contradictory | 23 | 15 | 8 | 0.8205 | 1.0000 |
| prevalence_random | D4_stale_reference_data | 14 | 14 | 0 | 0.7273 | 1.0000 |
| prevalence_random | D5_boundary_error | 18 | 18 | 0 | 0.8750 | 1.0000 |
| prevalence_random | D6_dead_code | 23 | 11 | 12 | 0.7568 | 1.0000 |
| prevalence_random | D7_conformant | 43 | 39 | 4 | 0.0000 | 1.0000 |
| static_keyword | D1_stale_threshold | 61 | 49 | 12 | 0.6136 | 1.0000 |
| static_keyword | D2_missing_rule | 14 | 14 | 0 | 0.9231 | 1.0000 |
| static_keyword | D3_contradictory | 23 | 15 | 8 | 1.0000 | 1.0000 |
| static_keyword | D4_stale_reference_data | 14 | 14 | 0 | 1.0000 | 1.0000 |
| static_keyword | D5_boundary_error | 18 | 18 | 0 | 0.0000 | 1.0000 |
| static_keyword | D6_dead_code | 23 | 11 | 12 | 0.6857 | 1.0000 |
| static_keyword | D7_conformant | 43 | 39 | 4 | 0.0000 | 1.0000 |
| attacker_with_bases | D1_stale_threshold | 61 | 49 | 12 | 1.0000 | 1.0000 |
| attacker_with_bases | D2_missing_rule | 14 | 14 | 0 | 1.0000 | 1.0000 |
| attacker_with_bases | D3_contradictory | 23 | 15 | 8 | 1.0000 | 1.0000 |
| attacker_with_bases | D4_stale_reference_data | 14 | 14 | 0 | 1.0000 | 1.0000 |
| attacker_with_bases | D5_boundary_error | 18 | 18 | 0 | 1.0000 | 1.0000 |
| attacker_with_bases | D6_dead_code | 23 | 11 | 12 | 1.0000 | 1.0000 |
| attacker_with_bases | D7_conformant | 43 | 39 | 4 | 0.0000 | 1.0000 |

## Structured T2 localization and T3 classification

| System | T3 macro-F1 | Program Acc@1 | Paragraph Acc@1 | Line Acc@1 | Line overlap |
|---|---:|---:|---:|---:|---:|
| agent | 0.2574 | 0.2288 | 0.1895 | 0.0850 | 0.0621 |
| plain_llm | 0.2288 | 0.6013 | 0.4967 | 0.0588 | 0.0381 |
| rag_dense | 0.2284 | 0.6144 | 0.4902 | 0.0588 | 0.0566 |
| rag_reranker | 0.3019 | 0.6732 | 0.5556 | 0.0196 | 0.0377 |
| oracle_slice | 0.0830 | 0.4902 | 0.2745 | 0.1569 | 0.1101 |

## Agent faithfulness, calibration, and coverage

Aggregate groundedness is 0.4048 over 42 answered rows. Clause evidence accuracy is 1.0000; code evidence accuracy is 0.4048. Per-tier evidence remains: `{"1": {"faithfulness": 0.0, "n": 5}, "2": {"faithfulness": 0.6956521739130435, "n": 23}, "3": {"faithfulness": 0.07142857142857142, "n": 14}}`.

Brier score 0.2017; ECE 0.1333. Coverage is 0.2143. Risk-coverage data remains machine-readable in the JSON artifact.

## T6 temporal evidence

T6 is 1/9 (0.1111), exact 95% CI [0.0028, 0.4825]. Status remains **NOT_EVALUABLE_FOR_BAR** because 20 pairs are required. This is directional evidence only.

## Anti-gaming handoff

The registered features do not distinguish the exactly balanced probe. The all-zero fit collapses to an all-drift prevalence baseline; F1 0.8768 is not evidence of a strong attacker and is not a pass/fail floor.

All six per-feature AUCs are exactly 0.5 and each drift/MO-0 sorted feature multiset is identical. All six fitted weights and the bias are zero. The old +0.10 agent-over-attacker floor remains **VACATED**.

## Cost, tools, and tokens

| System | Provider turns | Tokens | Tool calls | Answer rate |
|---|---:|---:|---:|---:|
| agent | 1372 | 33828531 | 4434 | 0.2143 |
| plain_llm | 196 | 1209656 | 0 | 0.5561 |
| rag_dense | 196 | 1211143 | 0 | 0.5408 |
| rag_reranker | 196 | 1107779 | 0 | 0.6378 |
| oracle_slice | 196 | 1721563 | 0 | 0.4898 |
| train_majority | 0 | not_recorded | 0 | 1.0000 |
| prevalence_random | 0 | not_recorded | 0 | 1.0000 |
| static_keyword | 0 | not_recorded | 0 | 1.0000 |
| attacker_with_bases | 0 | not_recorded | 0 | 1.0000 |

No dollar cost is estimated; provider calls were ChatGPT-authenticated and no metered billing record exists.

## Error-analysis summary

| System | Binary errors | Abstentions | Wrong class | Interprocedural failures |
|---|---:|---:|---:|---:|
| agent | 121 | 154 | 14 | 31 |
| plain_llm | 78 | 87 | 56 | 29 |
| rag_dense | 71 | 90 | 50 | 27 |
| rag_reranker | 72 | 71 | 56 | 27 |
| oracle_slice | 99 | 100 | 77 | 36 |

Categories may overlap. Root causes are not assigned beyond frozen trajectory support.

## CI fragility

Cells below ten rows remain CI-fragile:

- `D2_missing_rule/interprocedural`
- `D3_contradictory/interprocedural`
- `D4_stale_reference_data/interprocedural`
- `D5_boundary_error/interprocedural`
- `D7_conformant/interprocedural`

## Threats and limitations

- **synthetic_real_composition (limitation):** The 196-row test set mixes 153 synthetic and 43 real-curated rows; results do not isolate performance on a broad natural-code population.
- **real_curated_sample (limitation):** Only 43 of 51 reviewed real-curated candidates entered v1; eight were excluded under the frozen fail-closed adjudication protocol.
- **regulatory_scope (limitation):** The benchmark is limited to pinned RBI card/debit-card and KYC/AML clauses and their selected historical versions.
- **cobol_corpus_diversity (limitation):** The evaluated COBOL corpus is dominated by AWS CardDemo-derived and repository-native programs; IBM CICS CBSA is not consumed by benchmark v1.
- **materialized_context (limitation):** Systems consume reconstructed/materialized source bundles rather than an unrestricted production mainframe environment.
- **ci_fragile_strata (limitation):** Several class-by-locus cells contain fewer than ten rows; their point estimates do not support broad comparative claims.
- **temporal_pair_dependence (limitation):** T6 rows are paired by byte-identical code locus across clause versions and therefore are not independent single-row observations.
- **t6_pair_count (limitation):** Only nine intact T6 pairs remain, below the declared minimum of twenty for evaluating the formal reporting bar.
- **annotation_workflow (limitation):** Real-curated labels use one human-primary pass, a separate Claude verification pass, and human final review; agreement is not inter-human agreement.
- **model_provider_identity (limitation):** Provider-backed findings are specific to ChatGPT-authenticated gpt-5.6-luna and the recorded prompts, budgets, and verifier.
- **mixed_projection_provenance (limitation):** Agent, RAG+reranker, and oracle-slice projections mix reused M4 rows with targeted Phase-5 reruns and are descriptive comparisons, not controlled prompt/effort ablations.
- **agent_coverage (limitation):** The agent answered 42/196 rows and abstained on 154/196, so answered-subset accuracy cannot stand in for full-coverage performance.
- **drift_prevalence (limitation):** The test set is drift-heavy (153/196), inflating raw binary F1 for all-drift predictors and making balanced accuracy essential context.
- **track_b_crlf_manifest (known_cross_track_defect):** Track B's benchmark manifest still records stale CRLF split hashes; Phase-5 uses the ratified canonical LF identities without editing the Track B artifact.

## Next work

T7.5 paper and submission package; final completion still depends on T7.2/T7.3 release artifacts.

M8 remains planned post-release work and is not active.
