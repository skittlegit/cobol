# Detector report: test split

**Decision: NO_GO**

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.961 | >= 0.7 | yes |
| Balanced accuracy | 0.938 | >= 0.65 | yes |
| Answer rate | 0.991 | >= 0.6 | yes |
| Answered accuracy | 0.957 | >= 0.8 | yes |
| Interprocedural F1 vs rag_reranker | +0.071 (CI 0.023..0.139, p=0.0307, n=45) | >= +0.10, CI > 0, p < 0.05 | NO |
| Temporal paired accuracy | 22/22 = 1.000 | >= 0.7 on >= 20 pairs | yes |
| Unverified findings | 0 | 0 | yes |

## Confusion matrix (detector)

| gold \ predicted | D1 | D2 | D3 | D4 | D5 | D6 | D7 | ABST |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1_stale_threshold | 26 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| D2_missing_rule | 0 | 4 | 0 | 0 | 0 | 1 | 0 | 0 |
| D3_contradictory | 0 | 0 | 16 | 0 | 0 | 0 | 0 | 1 |
| D4_stale_reference_data | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| D5_boundary_error | 0 | 0 | 0 | 0 | 9 | 0 | 0 | 0 |
| D6_dead_code | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 0 |
| D7_conformant | 1 | 0 | 1 | 1 | 1 | 0 | 37 | 0 |
