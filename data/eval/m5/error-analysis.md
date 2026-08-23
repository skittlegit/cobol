# T5.4 Error Analysis — EVALUABLE

Deterministic categorization from frozen gold, predictions, verification records, and trajectories. Categories may overlap; each share names its own applicable denominator.

No root cause is assigned unless a frozen abstention reason or trajectory supports it.

## agent

| Category | Count | Applicable | Share | Representative IDs |
|---|---:|---:|---:|---|
| abstentions | 154 | 196 | 0.7857 | drift_000002, drift_000004, drift_000005, drift_000006, drift_000007 |
| evidence_verification_failures | 25 | 196 | 0.1276 | drift_000012, drift_024882, drift_110004, drift_110011, drift_110022 |
| false_negatives | 118 | 121 | 0.9752 | drift_000002, drift_000004, drift_000006, drift_000008, drift_000010 |
| false_positives | 3 | 121 | 0.0248 | drift_110011, drift_418841, drift_944771 |
| interprocedural_failures | 31 | 36 | 0.8611 | drift_000005, drift_000019, drift_000020, drift_000021, drift_052199 |
| localization_failures | 22 | 42 | 0.5238 | drift_000012, drift_024882, drift_110004, drift_110022, drift_110026 |
| wrong_drift_class | 14 | 42 | 0.3333 | drift_000014, drift_110004, drift_110011, drift_113091, drift_364039 |
| wrong_version_or_clause | 0 | 42 | 0.0000 | none |

Failure-mode evidence: `{"coverage_or_abstention_failure": 93, "insufficient_evidence": 61, "reasoning_or_classification_failure": 14, "retrieval_failure": 0, "root_cause_not_supported": 12, "slicing_or_context_failure": 0, "verifier_rejection": 0}`.

## plain_llm

| Category | Count | Applicable | Share | Representative IDs |
|---|---:|---:|---:|---|
| abstentions | 87 | 196 | 0.4439 | drift_000002, drift_000004, drift_000005, drift_000006, drift_000007 |
| evidence_verification_failures | 7 | 196 | 0.0357 | drift_000002, drift_358788, drift_617580, drift_635878, drift_776981 |
| false_negatives | 61 | 78 | 0.7821 | drift_000002, drift_000004, drift_000006, drift_000012, drift_000018 |
| false_positives | 17 | 78 | 0.2179 | drift_000015, drift_000017, drift_000019, drift_000020, drift_000021 |
| interprocedural_failures | 29 | 36 | 0.8056 | drift_000005, drift_000019, drift_000020, drift_000021, drift_052199 |
| localization_failures | 79 | 109 | 0.7248 | drift_000008, drift_000010, drift_000011, drift_000014, drift_016555 |
| wrong_drift_class | 56 | 109 | 0.5138 | drift_000011, drift_000013, drift_000014, drift_000015, drift_000017 |
| wrong_version_or_clause | 0 | 109 | 0.0000 | none |

Failure-mode evidence: `{"coverage_or_abstention_failure": 58, "insufficient_evidence": 9, "reasoning_or_classification_failure": 56, "retrieval_failure": 0, "root_cause_not_supported": 46, "slicing_or_context_failure": 13, "verifier_rejection": 7}`.

## rag_dense

| Category | Count | Applicable | Share | Representative IDs |
|---|---:|---:|---:|---|
| abstentions | 90 | 196 | 0.4592 | drift_000005, drift_000006, drift_000008, drift_000009, drift_000010 |
| evidence_verification_failures | 8 | 196 | 0.0408 | drift_000021, drift_046343, drift_096952, drift_191889, drift_356266 |
| false_negatives | 59 | 71 | 0.8310 | drift_000006, drift_000008, drift_000010, drift_000012, drift_000013 |
| false_positives | 12 | 71 | 0.1690 | drift_000007, drift_000015, drift_000019, drift_000020, drift_011604 |
| interprocedural_failures | 27 | 36 | 0.7500 | drift_000005, drift_000019, drift_000020, drift_000021, drift_052199 |
| localization_failures | 79 | 106 | 0.7453 | drift_000002, drift_000004, drift_000011, drift_000014, drift_016555 |
| wrong_drift_class | 50 | 106 | 0.4717 | drift_000002, drift_000004, drift_000007, drift_000011, drift_000014 |
| wrong_version_or_clause | 5 | 106 | 0.0472 | drift_000007, drift_110011, drift_110013, drift_110015, drift_110017 |

Failure-mode evidence: `{"coverage_or_abstention_failure": 56, "insufficient_evidence": 18, "reasoning_or_classification_failure": 50, "retrieval_failure": 5, "root_cause_not_supported": 47, "slicing_or_context_failure": 3, "verifier_rejection": 8}`.

## rag_reranker

| Category | Count | Applicable | Share | Representative IDs |
|---|---:|---:|---:|---|
| abstentions | 71 | 196 | 0.3622 | drift_000005, drift_000012, drift_000013, drift_000014, drift_000016 |
| evidence_verification_failures | 2 | 196 | 0.0102 | drift_110008, drift_110010 |
| false_negatives | 50 | 72 | 0.6944 | drift_000012, drift_000013, drift_000014, drift_000018, drift_046343 |
| false_positives | 22 | 72 | 0.3056 | drift_000007, drift_000009, drift_000015, drift_011604, drift_088851 |
| interprocedural_failures | 27 | 36 | 0.7500 | drift_000005, drift_000019, drift_000020, drift_000021, drift_052199 |
| localization_failures | 85 | 125 | 0.6800 | drift_000002, drift_000004, drift_000006, drift_000008, drift_000010 |
| wrong_drift_class | 56 | 125 | 0.4480 | drift_000002, drift_000004, drift_000006, drift_000007, drift_000009 |
| wrong_version_or_clause | 7 | 125 | 0.0560 | drift_000007, drift_000009, drift_110011, drift_110021, drift_110025 |

Failure-mode evidence: `{"coverage_or_abstention_failure": 49, "insufficient_evidence": 13, "reasoning_or_classification_failure": 56, "retrieval_failure": 0, "root_cause_not_supported": 59, "slicing_or_context_failure": 7, "verifier_rejection": 2}`.

## oracle_slice

| Category | Count | Applicable | Share | Representative IDs |
|---|---:|---:|---:|---|
| abstentions | 100 | 196 | 0.5102 | drift_000005, drift_000007, drift_000015, drift_000016, drift_000018 |
| evidence_verification_failures | 1 | 196 | 0.0051 | drift_785915 |
| false_negatives | 78 | 99 | 0.7879 | drift_000018, drift_003896, drift_016555, drift_024379, drift_035337 |
| false_positives | 21 | 99 | 0.2121 | drift_000009, drift_000017, drift_000019, drift_000020, drift_000021 |
| interprocedural_failures | 36 | 36 | 1.0000 | drift_000005, drift_000019, drift_000020, drift_000021, drift_052199 |
| localization_failures | 40 | 96 | 0.4167 | drift_000004, drift_000011, drift_000012, drift_024882, drift_046343 |
| wrong_drift_class | 77 | 96 | 0.8021 | drift_000002, drift_000004, drift_000006, drift_000009, drift_000010 |
| wrong_version_or_clause | 0 | 96 | 0.0000 | none |

Failure-mode evidence: `{"coverage_or_abstention_failure": 26, "insufficient_evidence": 3, "reasoning_or_classification_failure": 77, "retrieval_failure": 0, "root_cause_not_supported": 6, "slicing_or_context_failure": 71, "verifier_rejection": 0}`.
