# Detector report: dev split

**Decision: DEV_ONLY**

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.943 | >= 0.7 | yes |
| Balanced accuracy | 0.876 | >= 0.65 | yes |
| Answer rate | 0.981 | >= 0.6 | yes |
| Answered accuracy | 0.927 | >= 0.8 | yes |
| Interprocedural F1 vs rag_reranker | +nan (CI nan..nan, p=nan, n=0) | >= +0.10, CI > 0, p < 0.05 | NO |
| Temporal paired accuracy | 0/22 = 0.000 | >= 0.7 on >= 20 pairs | NO |
| Unverified findings | 0 | 0 | yes |

## Confusion matrix (detector)

| gold \ predicted | D1 | D2 | D3 | D4 | D5 | D6 | D7 | ABST |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1_stale_threshold | 88 | 0 | 6 | 0 | 0 | 0 | 2 | 0 |
| D2_missing_rule | 2 | 24 | 0 | 0 | 0 | 0 | 0 | 0 |
| D3_contradictory | 0 | 0 | 37 | 0 | 0 | 0 | 0 | 1 |
| D4_stale_reference_data | 0 | 3 | 0 | 15 | 0 | 0 | 0 | 0 |
| D5_boundary_error | 2 | 0 | 2 | 0 | 31 | 0 | 0 | 1 |
| D6_dead_code | 0 | 0 | 1 | 0 | 0 | 13 | 7 | 2 |
| D7_conformant | 3 | 4 | 4 | 0 | 3 | 0 | 67 | 2 |
