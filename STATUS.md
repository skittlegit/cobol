# Status

Updated 2026-10-08.

## Current result

**E1 (first-look official run): NO_GO.** Temporal paired accuracy 15/22
against 0.70; every other gate passed. See [E1](docs/tasks/E1.md).

**E2 (evaluation after fixing E1's failures): in progress.** The detector is
being tuned on realistic-size cross-program dev rows before it is frozen and
run once on a fresh 95-row test split. See [E2](docs/tasks/E2.md).

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
| E2 | Evaluation after fixing E1's failures | in progress | [E2](docs/tasks/E2.md) |
| M1 | Simplify migration | done | [M1](docs/tasks/M1.md) |
| P1 | Regenerate paper, datasheet, and release | done | [P1](docs/tasks/P1.md) |
| S1 | Project site generated from the canonical results | done | [S1](docs/tasks/S1.md) |

Order: D4 → D5 → B1/B2 → E1 → P1/S1.
