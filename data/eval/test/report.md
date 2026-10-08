# Detector report: test split

**Decision: NO_GO**

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.882 | >= 0.7 | yes |
| Balanced accuracy | 0.842 | >= 0.65 | yes |
| Answer rate | 1.000 | >= 0.6 | yes |
| Answered accuracy | 0.848 | >= 0.8 | yes |
| Interprocedural F1 vs rag_reranker | +0.165 (CI 0.089..0.258, p=0.0001, n=60) | >= +0.10, CI > 0, p < 0.05 | yes |
| Temporal paired accuracy | 15/22 = 0.682 | >= 0.7 on >= 20 pairs | NO |
| Unverified findings | 0 | 0 | yes |

## Confusion matrix (detector)

| gold \ predicted | D1 | D2 | D3 | D4 | D5 | D6 | D7 | ABST |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1_stale_threshold | 31 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| D2_missing_rule | 0 | 4 | 2 | 0 | 0 | 0 | 0 | 0 |
| D3_contradictory | 0 | 0 | 21 | 0 | 0 | 0 | 0 | 0 |
| D4_stale_reference_data | 0 | 1 | 0 | 4 | 0 | 0 | 0 | 0 |
| D5_boundary_error | 0 | 0 | 0 | 0 | 9 | 0 | 0 | 0 |
| D6_dead_code | 0 | 5 | 1 | 0 | 0 | 4 | 12 | 0 |
| D7_conformant | 2 | 7 | 0 | 0 | 0 | 0 | 41 | 0 |
