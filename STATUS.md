# Status

Updated 2026-10-08.

## Current result

**E2 (evaluation after fixing E1's failures, 2026-10-08): GO.** A fresh
95-row held-out split, with 72 cross-program rows (realistic-size bundles,
conformant cases included), and 22 temporal pairs. The detector was frozen
before the run (method hash f48061167cfd7a0f; gpt-6-luna at `max`), and the
gates are unchanged.

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.927 | >= 0.70 | yes |
| Balanced accuracy | 0.909 | >= 0.65 | yes |
| Answer rate | 1.000 | >= 0.60 | yes |
| Answered accuracy | 0.916 | >= 0.80 | yes |
| Interprocedural F1 vs rag_reranker | +0.190, CI 0.058..0.340, p < 0.001, n = 72 | +0.10, CI > 0, p < 0.05 | yes |
| Temporal paired accuracy | 20/22 = 0.909 | >= 0.70 on >= 20 pairs | yes |
| Unverified findings | 0 | 0 | yes |

The main weakness is false alarms on conformant code: 8 of 44 conformant
rows were called D3, half of them on a region gate in the benchmark's chain
hosts. E2 is post hoc with respect to E1. Details are in
[E2](docs/tasks/E2.md).

**E1 (first-look official run): NO_GO.** Temporal paired accuracy 15/22
against 0.70; every other gate passed. See [E1](docs/tasks/E1.md).

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
| E2 | Evaluation after fixing E1's failures (GO) | done | [E2](docs/tasks/E2.md) |
| M1 | Simplify migration | done | [M1](docs/tasks/M1.md) |
| P1 | Regenerate paper, datasheet, and release | done | [P1](docs/tasks/P1.md) |
| S1 | Project site generated from the canonical results | done | [S1](docs/tasks/S1.md) |

Order: D4 → D5 → B1/B2 → E1 → E2 → P1/S1.
