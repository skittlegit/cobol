# Status

Updated 2026-10-07.

## Current result

**E3 (third evaluation, 2026-10-08): NO_GO.** Fresh 116-row test split and 22
fresh temporal pairs, written and checked before the run; the same frozen
detector (method files identical to ea5db367, gpt-6-luna at `max`); gates
unchanged.

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.961 | >= 0.70 | yes |
| Balanced accuracy | 0.938 | >= 0.65 | yes |
| Answer rate | 0.991 | >= 0.60 | yes |
| Answered accuracy | 0.957 | >= 0.80 | yes |
| Interprocedural F1 vs rag_reranker | +0.071, CI 0.023..0.139, p = 0.031, n = 45 | +0.10, CI > 0, p < 0.05 | no |
| Temporal paired accuracy | 22/22 = 1.000 | >= 0.70 on >= 20 pairs | yes |
| Unverified findings | 0 | 0 | yes |

The only failing gate is the margin over the baseline: on cross-program rows
the detector is perfect (F1 1.000) but the baseline reaches 0.929, so the
margin cannot reach 0.10. D6 recall is 15/15 (4/22 in E1). Details in
[E3](docs/tasks/E3.md).

Earlier runs: **E1 NO_GO** (temporal 15/22; flawed temporal programs),
**E2 GO** (post-hoc, after correcting those programs). See
[E1](docs/tasks/E1.md) and [E2](docs/tasks/E2.md).

## Tasks

| ID | Task | State | Record |
| --- | --- | --- | --- |
| C1 | Consolidate the repository to one clean version | done | [C1](docs/tasks/C1.md) |
| D1 | Host-computed evidence-ledger hashes | done | [D1](docs/tasks/D1.md) |
| D2 | `check_finding` self-check inside the task | done (offline) | [D2](docs/tasks/D2.md) |
| D3 | Error analysis of the last official run | done | [D3](docs/tasks/D3.md) |
| D4 | Detector improvements: D6, D7-vs-D2, temporal | done | [D4](docs/tasks/D4.md) |
| D5 | Live dev runs and tuning (dev balanced accuracy 0.876) | done | [D5](docs/tasks/D5.md) |
| B1 | Fresh held-out test split (145 rows) | done | [B1](docs/tasks/B1.md) |
| B2 | Fresh temporal pairs (22) | done | [B2](docs/tasks/B2.md) |
| E1 | Official run and decision (NO_GO) | done | [E1](docs/tasks/E1.md) |
| E2 | Second evaluation: corrected temporal programs, same detector (GO) | done | [E2](docs/tasks/E2.md) |
| E3 | Third evaluation: fresh test split and temporal pairs, same detector (NO_GO) | done | [E3](docs/tasks/E3.md) |
| M1 | Simplify migration | done | [M1](docs/tasks/M1.md) |
| P1 | Regenerate paper, datasheet, and release | done | [P1](docs/tasks/P1.md) |
| S1 | Project site generated from the canonical results | done | [S1](docs/tasks/S1.md) |

Order: D4 → D5 → B1/B2 → E1 → P1/S1.
