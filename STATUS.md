# Status

Updated 2026-10-07.

## Current result

The official run (E1, 2026-10-08; detector frozen at commit ea5db367,
gpt-6-luna at effort `max`; fresh 145-row test split and 22 temporal pairs) is
**NO_GO**. Six of seven gates pass; temporal paired accuracy misses by one
pair.

| Gate | Measured | Required | Pass |
| --- | --- | --- | --- |
| T1 F1 | 0.882 | >= 0.70 | yes |
| Balanced accuracy | 0.842 | >= 0.65 | yes |
| Answer rate | 1.000 | >= 0.60 | yes |
| Answered accuracy | 0.848 | >= 0.80 | yes |
| Interprocedural F1 vs rag_reranker | +0.165, CI 0.089..0.258, p = 0.0001, n = 60 | +0.10, CI > 0, p < 0.05 | yes |
| Temporal paired accuracy | 15/22 = 0.682 | >= 0.70 on >= 20 pairs | no |
| Unverified findings | 0 | 0 | yes |

Diagnosis (reported, not used to change the decision): 5 of the 7 failed
pairs fail on the old, conformant side, which the detector called D2. In at
least four of them (TPCO04, TPCO06, TPCO08, TPTR07) the detector is right: the
programs written for B2 omit part of the clause (a capital or profits leg, the
control route, the author and trustee roles), so their conformant label is
wrong. Test D6 recall is 4/22: most fresh chain hosts were called D7 or D2.
Full report: `data/eval/test/report.md`; details in `docs/tasks/E1.md`.

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
| M1 | Simplify migration | done | [M1](docs/tasks/M1.md) |
| P1 | Regenerate paper, datasheet, and release | done | [P1](docs/tasks/P1.md) |
| S1 | Project site generated from the canonical results | in progress | [S1](docs/tasks/S1.md) |

Order: D4 → D5 → B1/B2 → E1 → P1/S1.
