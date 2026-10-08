# Detector report: test split

**Decision: GO**

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.927 | >= 0.7 | yes |
| Balanced accuracy | 0.909 | >= 0.65 | yes |
| Answer rate | 1.000 | >= 0.6 | yes |
| Answered accuracy | 0.916 | >= 0.8 | yes |
| Interprocedural F1 vs rag_reranker | +0.190 (CI 0.058..0.340, p=0.0000, n=72) | >= +0.10, CI > 0, p < 0.05 | yes |
| Temporal paired accuracy | 20/22 = 0.909 | >= 0.7 on >= 20 pairs | yes |
| Unverified findings | 0 | 0 | yes |

## Confusion matrix (detector)

| gold \ predicted | D1 | D2 | D3 | D4 | D5 | D6 | D7 | ABST |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1_stale_threshold | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| D2_missing_rule | 0 | 3 | 0 | 0 | 0 | 1 | 0 | 0 |
| D3_contradictory | 0 | 0 | 12 | 0 | 0 | 0 | 0 | 0 |
| D4_stale_reference_data | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| D5_boundary_error | 0 | 0 | 0 | 0 | 5 | 0 | 0 | 0 |
| D6_dead_code | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 0 |
| D7_conformant | 0 | 0 | 8 | 0 | 0 | 0 | 36 | 0 |
