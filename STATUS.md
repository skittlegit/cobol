# Status

Updated 2026-10-07.

## Current result

The last official run (gpt-6-luna/max, 196 test rows, 20 temporal pairs),
re-scored by `eval/report.py`, is **NO_GO**:

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.780 | >= 0.70 | yes |
| Balanced accuracy | 0.527 | >= 0.65 | no |
| Answer rate | 0.709 | >= 0.60 | yes |
| Answered accuracy | 0.885 | >= 0.80 | yes |
| Interprocedural F1 vs rag_reranker | +0.259, CI 0.027..0.500, p = 0.0512 | +0.10, CI > 0, p < 0.05 | no |
| Temporal paired accuracy | 7/20 = 0.35 | >= 0.70 | no |
| Unverified findings | 0 | 0 | yes |

The earlier `NOT_EVALUABLE` label came from four evidence-ledger hashes the
model had copied incorrectly. Hashes are now computed by the host (D1), so
that failure mode no longer exists.

That test split had been opened repeatedly, so its 196 rows were folded into
`dev` (now 320 rows, including the 40 rows of the previous temporal pairs) and their results moved to `data/eval/dev/`
(`report.md` there, decision `DEV_ONLY`). The fresh test split (B1, 145 rows,
60 interprocedural) and the fresh temporal set (B2, 22 pairs) are built and
have not been run; the official report stays
`NOT_EVALUABLE` until E1.

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
| E1 | Official run and decision | in progress | [E1](docs/tasks/E1.md) |
| M1 | Simplify migration | done | [M1](docs/tasks/M1.md) |
| P1 | Regenerate paper, datasheet, and release | todo | [P1](docs/tasks/P1.md) |
| S1 | Project site generated from the canonical results | in progress | [S1](docs/tasks/S1.md) |

Order: D4 → D5 → B1/B2 → E1 → P1/S1.
