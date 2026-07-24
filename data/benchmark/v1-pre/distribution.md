# Benchmark v1-pre Distribution

Deterministic seed: `2600`. Target ratios: train 70%, dev 15%, test 15%.
Base-program grouping, roster reservations, and real-curated test reservation are hard constraints;
T6 verdict-flipping pairs: **20**.

## Frozen JSONL hashes

| file | SHA-256 |
|---|---|
| train.jsonl | `4b333851b97629083bfb753cbed28a0c47a5cbe5376d270731b7eb47ab982763` |
| dev.jsonl | `31842be32741d00c970e4d1f50d9a38e22774e3455cb9300922bc642a1b0ffef` |
| test.jsonl | `5e8fb3676aab8ff2f886d72c6faab2c1a4b60f2595a3374eaa400e35f3d31d58` |
`CI-fragile` marks every split × class × stratum cell with n < 10.

## Split summary

| split | total | synthetic | real_curated | local | interprocedural | base groups |
|---|---:|---:|---:|---:|---:|---:|
| train | 307 | 307 | 0 | 300 | 7 | 21 |
| dev | 102 | 102 | 0 | 102 | 0 | 4 |
| test | 204 | 153 | 51 | 168 | 36 | 38 |

## Purpose-level gates

| gate | required | observed | status |
|---|---:|---:|---|
| train synthetic share | >= 40% | 54.6% | pass |
| dev synthetic share | >= 12% | 18.1% | pass |
| test interprocedural | >= 30 | 36 | pass |
| train classes | >= 5 | 7 | pass |
| dev classes | >= 5 | 6 | pass |

### Test interprocedural operator coverage

| operator | required | observed | status |
|---|---:|---:|---|
| MO-1× | >= 8 | 12 | pass |
| MO-3× | >= 8 | 8 | pass |
| MO-6× | >= 8 | 12 | pass |

### Test interprocedural class shortfalls

A zero is an explicit purpose-gate shortfall: no accepted interprocedural mutation currently emits that class.

| class | n | coverage |
|---|---:|---|
| D1_stale_threshold | 13 | covered |
| D2_missing_rule | 1 | covered |
| D3_contradictory | 8 | covered |
| D4_stale_reference_data | 0 | named shortfall |
| D5_boundary_error | 0 | named shortfall |
| D6_dead_code | 13 | covered |

## Split × class × stratum cells

| split | class | stratum | n | CI status |
|---|---|---|---:|---|
| train | D1_stale_threshold | local | 54 | ok |
| train | D1_stale_threshold | interprocedural | 0 | CI-fragile |
| train | D2_missing_rule | local | 32 | ok |
| train | D2_missing_rule | interprocedural | 0 | CI-fragile |
| train | D3_contradictory | local | 19 | ok |
| train | D3_contradictory | interprocedural | 7 | CI-fragile |
| train | D4_stale_reference_data | local | 2 | CI-fragile |
| train | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| train | D5_boundary_error | local | 67 | ok |
| train | D5_boundary_error | interprocedural | 0 | CI-fragile |
| train | D6_dead_code | local | 23 | ok |
| train | D6_dead_code | interprocedural | 0 | CI-fragile |
| train | D7_conformant | local | 103 | ok |
| train | D7_conformant | interprocedural | 0 | CI-fragile |
| dev | D1_stale_threshold | local | 29 | ok |
| dev | D1_stale_threshold | interprocedural | 0 | CI-fragile |
| dev | D2_missing_rule | local | 8 | CI-fragile |
| dev | D2_missing_rule | interprocedural | 0 | CI-fragile |
| dev | D3_contradictory | local | 15 | ok |
| dev | D3_contradictory | interprocedural | 0 | CI-fragile |
| dev | D4_stale_reference_data | local | 4 | CI-fragile |
| dev | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| dev | D5_boundary_error | local | 17 | ok |
| dev | D5_boundary_error | interprocedural | 0 | CI-fragile |
| dev | D6_dead_code | local | 0 | CI-fragile |
| dev | D6_dead_code | interprocedural | 0 | CI-fragile |
| dev | D7_conformant | local | 29 | ok |
| dev | D7_conformant | interprocedural | 0 | CI-fragile |
| test | D1_stale_threshold | local | 47 | ok |
| test | D1_stale_threshold | interprocedural | 13 | ok |
| test | D2_missing_rule | local | 10 | ok |
| test | D2_missing_rule | interprocedural | 1 | CI-fragile |
| test | D3_contradictory | local | 16 | ok |
| test | D3_contradictory | interprocedural | 8 | CI-fragile |
| test | D4_stale_reference_data | local | 14 | ok |
| test | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| test | D5_boundary_error | local | 19 | ok |
| test | D5_boundary_error | interprocedural | 0 | CI-fragile |
| test | D6_dead_code | local | 10 | ok |
| test | D6_dead_code | interprocedural | 13 | ok |
| test | D7_conformant | local | 52 | ok |
| test | D7_conformant | interprocedural | 1 | CI-fragile |

## Base-program assignment

| base group | split | synthetic | real_curated | total |
|---|---|---:|---:|---:|
| ACTIVAT1 | dev | 31 | 0 | 31 |
| ACTRECON2 | train | 4 | 0 | 4 |
| BATCHCT2 | test | 12 | 0 | 12 |
| BOIDENT1 | test | 0 | 2 | 2 |
| BOIDENT2 | test | 21 | 1 | 22 |
| BOIDENT3 | dev | 32 | 0 | 32 |
| CBACT04C | test | 0 | 1 | 1 |
| CBTRN02C | test | 0 | 3 | 3 |
| CICREP1 | train | 30 | 0 | 30 |
| CICROLL2 | train | 4 | 0 | 4 |
| CKYQUEUE2 | train | 4 | 0 | 4 |
| CLOSPEN1 | test | 0 | 2 | 2 |
| CLOSPEN2 | test | 0 | 2 | 2 |
| CLOSPEN3 | test | 17 | 1 | 18 |
| CLOSPEN4 | test | 0 | 1 | 1 |
| CLOSPEN5 | test | 7 | 0 | 7 |
| CLOSPEN6 | train | 32 | 0 | 32 |
| CLOSPN5D | test | 0 | 1 | 1 |
| CLSRUN7 | test | 3 | 0 | 3 |
| GRVAGE1 | test | 0 | 2 | 2 |
| GRVAGE2 | train | 31 | 0 | 31 |
| INTCOMP1 | train | 32 | 0 | 32 |
| INTROLL2 | train | 4 | 0 | 4 |
| KYCSCHED1 | test | 20 | 1 | 21 |
| KYCSCHED2 | train | 29 | 0 | 29 |
| KYCSY201 | test | 1 | 0 | 1 |
| KYCSY202 | test | 1 | 0 | 1 |
| KYCSY203 | train | 1 | 0 | 1 |
| KYCSY204 | train | 1 | 0 | 1 |
| KYCSY205 | train | 1 | 0 | 1 |
| KYCSY206 | train | 1 | 0 | 1 |
| KYCSY207 | train | 1 | 0 | 1 |
| KYCSY208 | train | 1 | 0 | 1 |
| KYCSYNC1 | test | 0 | 2 | 2 |
| KYCSYNC2 | test | 22 | 1 | 23 |
| KYCSYNC3 | train | 31 | 0 | 31 |
| LATEFEE1 | test | 15 | 1 | 16 |
| LATEFEE2 | dev | 35 | 0 | 35 |
| NOTICE1 | train | 32 | 0 | 32 |
| OVDCHK1 | test | 7 | 0 | 7 |
| OVDROUT2 | train | 2 | 0 | 2 |
| OVRLIM1 | train | 7 | 0 | 7 |
| REFADJ1 | train | 32 | 0 | 32 |
| REFADJ2 | test | 12 | 0 | 12 |
| SANCBAT2 | dev | 4 | 0 | 4 |
| SCRNGATE1 | test | 7 | 0 | 7 |
| T6BO01 | test | 0 | 2 | 2 |
| T6BO02 | test | 0 | 2 | 2 |
| T6BO03 | test | 0 | 2 | 2 |
| T6BO04 | test | 0 | 2 | 2 |
| T6BO05 | test | 0 | 2 | 2 |
| T6CL01 | test | 0 | 2 | 2 |
| T6CL02 | test | 0 | 2 | 2 |
| T6CL03 | test | 0 | 2 | 2 |
| T6CL04 | test | 0 | 2 | 2 |
| T6CL05 | test | 0 | 2 | 2 |
| T6KYC01 | test | 0 | 2 | 2 |
| T6KYC02 | test | 0 | 2 | 2 |
| T6KYC03 | test | 0 | 2 | 2 |
| T6KYC04 | test | 0 | 2 | 2 |
| T6KYC05 | test | 0 | 2 | 2 |
| TRNVAL1 | test | 8 | 0 | 8 |
| UNSOLIC1 | train | 27 | 0 | 27 |
