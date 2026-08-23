# T5.4 Frozen Phase-5 Headline Experiment — EVALUABLE

## Headline result

On the frozen 36-row interprocedural stratum, agent underperformed the strongest frozen non-agentic model baseline.

Agent F1 0.4000 versus RAG+reranker 0.6939; ΔF1 -0.2939, 95% paired bootstrap CI [-0.4990, -0.1101], paired randomization p=0.0117 (n=36).

This is the measured frozen result. No provider run or post-result configuration change occurred.

## Artifact validity

| System | Rows | Artifact SHA-256 | Infrastructure failures |
|---|---:|---|---:|
| agent | 196 | `539782c99172f37bbc411adeb141a8c4e9b22f378b4f2d9e304a25ecd4a207a1` | 0 |
| plain_llm | 196 | `ff7c4de11169dc0d1625d26f2a1dcdc270261e24d30f84ba40d73adfa0eff945` | 0 |
| rag_dense | 196 | `3c7b2bb487e6724c174bb84c0fd3574cda75406aabfadc62d262c798d6109d0d` | 0 |
| rag_reranker | 196 | `06de52ab941fa34cc0b9fffb8945f6fa0c4b77dba1e90e19a0c8a340d0d95e87` | 0 |
| oracle_slice | 196 | `548a51890ef89489d52a3803348cee4ae91a54698ef842882ebe2db294a80215` | 0 |
| train_majority | 196 | `909b683e3726187f9e3e7f56f12c12e24eb1ab9ad520fd2040072fc6f3b9a109` | 0 |
| prevalence_random | 196 | `184e166ae35b283f22078aedf2061dd33a1baa94fcb76052a226b644f2f8b4e3` | 0 |
| static_keyword | 196 | `026a3ff5de01e0ab6c29612048bea4254f1f794d48240bd78d67db25aea31311` | 0 |
| attacker_with_bases | 196 | `5439aa34e2e27c83588501b2cc761412b1c97531bf448f47e7e8639b185eceb6` | 0 |

The benchmark uses the canonical LF identity `bc9e775a727d82c7d5a30fd0495512bffde173bec2580e3d08664b8d98b2aed4`; all systems match the same ordered 196 IDs.

## T1 detection

| System | Overall F1 | Local F1 | Interprocedural F1 | Balanced accuracy | Answer rate |
|---|---:|---:|---:|---:|---:|
| agent | 0.3665 | 0.3576 | 0.4000 | 0.1493 | 0.2143 |
| plain_llm | 0.7023 | 0.7324 | 0.5714 | 0.3007 | 0.5561 |
| rag_dense | 0.7259 | 0.7642 | 0.5532 | 0.3072 | 0.5408 |
| rag_reranker | 0.7410 | 0.7511 | 0.6939 | 0.3366 | 0.6378 |
| oracle_slice | 0.6024 | 0.6305 | 0.4783 | 0.2451 | 0.4898 |
| train_majority | 0.8768 | 0.8612 | 0.9412 | 0.5000 | 1.0000 |
| prevalence_random | 0.7331 | 0.7085 | 0.8276 | 0.5459 | 1.0000 |
| static_keyword | 0.7040 | 0.6120 | 0.9552 | 0.6829 | 1.0000 |
| attacker_with_bases | 0.8768 | 0.8612 | 0.9412 | 0.5000 | 1.0000 |

## D1–D7 class strata

The table reports full-coverage T1 within each gold class. Structured T3 precision/recall/F1 and confusion matrices are retained in `report.json`; binary-only static output cannot emit a D1–D7 class.

| System | Class | n | Local | Interproc. | T1 F1 | Answer rate | Fragility |
|---|---|---:|---:|---:|---:|---:|---|
| agent | D1_stale_threshold | 61 | 49 | 12 | 0.2817 | 0.1803 | none |
| agent | D2_missing_rule | 14 | 14 | 0 | 0.3529 | 0.2143 | interprocedural |
| agent | D3_contradictory | 23 | 15 | 8 | 0.1600 | 0.0870 | interprocedural |
| agent | D4_stale_reference_data | 14 | 14 | 0 | 0.6667 | 0.5000 | interprocedural |
| agent | D5_boundary_error | 18 | 18 | 0 | 0.7143 | 0.5556 | interprocedural |
| agent | D6_dead_code | 23 | 11 | 12 | 0.2308 | 0.1304 | none |
| agent | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.1395 | interprocedural |
| rag_reranker | D1_stale_threshold | 61 | 49 | 12 | 0.9298 | 0.8689 | none |
| rag_reranker | D2_missing_rule | 14 | 14 | 0 | 0.5263 | 0.3571 | interprocedural |
| rag_reranker | D3_contradictory | 23 | 15 | 8 | 0.8500 | 0.7391 | interprocedural |
| rag_reranker | D4_stale_reference_data | 14 | 14 | 0 | 0.4444 | 0.2857 | interprocedural |
| rag_reranker | D5_boundary_error | 18 | 18 | 0 | 1.0000 | 1.0000 | interprocedural |
| rag_reranker | D6_dead_code | 23 | 11 | 12 | 0.4138 | 0.2609 | none |
| rag_reranker | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.5116 | interprocedural |
| rag_dense | D1_stale_threshold | 61 | 49 | 12 | 0.8704 | 0.7705 | none |
| rag_dense | D2_missing_rule | 14 | 14 | 0 | 0.7826 | 0.6429 | interprocedural |
| rag_dense | D3_contradictory | 23 | 15 | 8 | 0.8500 | 0.7391 | interprocedural |
| rag_dense | D4_stale_reference_data | 14 | 14 | 0 | 0.4444 | 0.2857 | interprocedural |
| rag_dense | D5_boundary_error | 18 | 18 | 0 | 0.8750 | 0.7778 | interprocedural |
| rag_dense | D6_dead_code | 23 | 11 | 12 | 0.2308 | 0.1304 | none |
| rag_dense | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.2791 | interprocedural |
| plain_llm | D1_stale_threshold | 61 | 49 | 12 | 0.8598 | 0.7541 | none |
| plain_llm | D2_missing_rule | 14 | 14 | 0 | 0.5263 | 0.3571 | interprocedural |
| plain_llm | D3_contradictory | 23 | 15 | 8 | 0.8780 | 0.7826 | interprocedural |
| plain_llm | D4_stale_reference_data | 14 | 14 | 0 | 0.4444 | 0.2857 | interprocedural |
| plain_llm | D5_boundary_error | 18 | 18 | 0 | 0.8000 | 0.6667 | interprocedural |
| plain_llm | D6_dead_code | 23 | 11 | 12 | 0.4667 | 0.3043 | none |
| plain_llm | D7_conformant | 43 | 39 | 4 | 0.0000 | 0.3953 | interprocedural |
| static_keyword | D1_stale_threshold | 61 | 49 | 12 | 0.6136 | 1.0000 | none |
| static_keyword | D2_missing_rule | 14 | 14 | 0 | 0.9231 | 1.0000 | interprocedural |
| static_keyword | D3_contradictory | 23 | 15 | 8 | 1.0000 | 1.0000 | interprocedural |
| static_keyword | D4_stale_reference_data | 14 | 14 | 0 | 1.0000 | 1.0000 | interprocedural |
| static_keyword | D5_boundary_error | 18 | 18 | 0 | 0.0000 | 1.0000 | interprocedural |
| static_keyword | D6_dead_code | 23 | 11 | 12 | 0.6857 | 1.0000 | none |
| static_keyword | D7_conformant | 43 | 39 | 4 | 0.0000 | 1.0000 | interprocedural |

## Structured localization and classification

| System | T3 macro-F1 | Program Acc@1 | Paragraph Acc@1 | Line Acc@1 | Line overlap |
|---|---:|---:|---:|---:|---:|
| agent | 0.2574 | 0.2288 | 0.1895 | 0.0850 | 0.0621 |
| plain_llm | 0.2288 | 0.6013 | 0.4967 | 0.0588 | 0.0381 |
| rag_dense | 0.2284 | 0.6144 | 0.4902 | 0.0588 | 0.0566 |
| rag_reranker | 0.3019 | 0.6732 | 0.5556 | 0.0196 | 0.0377 |
| oracle_slice | 0.0830 | 0.4902 | 0.2745 | 0.1569 | 0.1101 |

## Agent faithfulness, calibration, and coverage

- Aggregate groundedness: 0.4048 (n=42).
- Per-tier groundedness: Tier 1 0.0000 (n=5), Tier 2 0.6957 (n=23), Tier 3 0.0714 (n=14).
- Clause evidence accuracy: 1.0000; code evidence accuracy: 0.4048.
- Brier score: 0.2017; ECE: 0.1333.
- Answered 42/196 (0.2143); abstained 154/196 (0.7857).
- Low coverage is part of the headline full-coverage result; unanswered rows are not discarded.

## T6 temporal pairs

1 successes and 8 failures across 9 pairs; paired accuracy 0.1111, exact 95% CI [0.0028, 0.4825]. Status: **NOT_EVALUABLE_FOR_BAR** because 20 pairs are required.

## Cost and efficiency

| System | Turns | Tokens recorded | Tool calls | Answer rate |
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

No dollar cost is estimated: provider runs were ChatGPT-authenticated and no metered billing record exists. Missing latency is reported as `not_recorded` in the JSON.

## Error analysis and frozen decisions

Reproducible category counts and representative IDs are in `error-analysis.json` and `error-analysis.md`.

The attacker surface floor remains **VACATED** and is not a pass/fail gate. The attacker remains null anti-gaming evidence.

CI-fragile cells (n < 10): D2_missing_rule/interprocedural, D3_contradictory/interprocedural, D4_stale_reference_data/interprocedural, D5_boundary_error/interprocedural, D7_conformant/interprocedural.

The frozen CONTRACT bars are reported in `report.json`; they do not change this report's `EVALUABLE` status into a tuning checkpoint.
