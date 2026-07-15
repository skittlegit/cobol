# Benchmark v1-pre Distribution

Deterministic seed: `2600`. Target ratios: train 70%, dev 15%, test 15%.
Base-program grouping, roster reservations, and real-curated test reservation are hard constraints;
`CI-fragile` marks every split × class × stratum cell with n < 10.

## Split summary

| split | total | synthetic | real_curated | local | interprocedural | base groups |
|---|---:|---:|---:|---:|---:|---:|
| train | 269 | 269 | 0 | 257 | 12 | 10 |
| dev | 82 | 82 | 0 | 82 | 0 | 3 |
| test | 199 | 178 | 21 | 163 | 36 | 17 |

## Purpose-level gates

| gate | required | observed | status |
|---|---:|---:|---|
| train synthetic share | >= 40% | 50.9% | pass |
| dev synthetic share | >= 12% | 15.5% | pass |
| test interprocedural | >= 30 | 36 | pass |
| train classes | >= 5 | 5 | pass |
| dev classes | >= 5 | 5 | pass |

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
| train | D1_stale_threshold | local | 84 | ok |
| train | D1_stale_threshold | interprocedural | 0 | CI-fragile |
| train | D2_missing_rule | local | 1 | CI-fragile |
| train | D2_missing_rule | interprocedural | 0 | CI-fragile |
| train | D3_contradictory | local | 9 | CI-fragile |
| train | D3_contradictory | interprocedural | 12 | ok |
| train | D4_stale_reference_data | local | 0 | CI-fragile |
| train | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| train | D5_boundary_error | local | 57 | ok |
| train | D5_boundary_error | interprocedural | 0 | CI-fragile |
| train | D6_dead_code | local | 0 | CI-fragile |
| train | D6_dead_code | interprocedural | 0 | CI-fragile |
| train | D7_conformant | local | 106 | ok |
| train | D7_conformant | interprocedural | 0 | CI-fragile |
| dev | D1_stale_threshold | local | 16 | ok |
| dev | D1_stale_threshold | interprocedural | 0 | CI-fragile |
| dev | D2_missing_rule | local | 0 | CI-fragile |
| dev | D2_missing_rule | interprocedural | 0 | CI-fragile |
| dev | D3_contradictory | local | 4 | CI-fragile |
| dev | D3_contradictory | interprocedural | 0 | CI-fragile |
| dev | D4_stale_reference_data | local | 0 | CI-fragile |
| dev | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| dev | D5_boundary_error | local | 18 | ok |
| dev | D5_boundary_error | interprocedural | 0 | CI-fragile |
| dev | D6_dead_code | local | 14 | ok |
| dev | D6_dead_code | interprocedural | 0 | CI-fragile |
| dev | D7_conformant | local | 30 | ok |
| dev | D7_conformant | interprocedural | 0 | CI-fragile |
| test | D1_stale_threshold | local | 32 | ok |
| test | D1_stale_threshold | interprocedural | 13 | ok |
| test | D2_missing_rule | local | 23 | ok |
| test | D2_missing_rule | interprocedural | 1 | CI-fragile |
| test | D3_contradictory | local | 16 | ok |
| test | D3_contradictory | interprocedural | 8 | CI-fragile |
| test | D4_stale_reference_data | local | 17 | ok |
| test | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| test | D5_boundary_error | local | 19 | ok |
| test | D5_boundary_error | interprocedural | 0 | CI-fragile |
| test | D6_dead_code | local | 15 | ok |
| test | D6_dead_code | interprocedural | 13 | ok |
| test | D7_conformant | local | 41 | ok |
| test | D7_conformant | interprocedural | 1 | CI-fragile |

## Base-program assignment

| base group | split | synthetic | real_curated | total |
|---|---|---:|---:|---:|
| ACTIVAT1 | train | 29 | 0 | 29 |
| BATCHCT2 | test | 12 | 0 | 12 |
| BOIDENT1 | test | 0 | 2 | 2 |
| BOIDENT2 | test | 20 | 1 | 21 |
| BOIDENT3 | train | 31 | 0 | 31 |
| CBACT04C | test | 0 | 1 | 1 |
| CBTRN02C | test | 0 | 3 | 3 |
| CICREP1 | train | 30 | 0 | 30 |
| CLOSPEN1 | test | 0 | 2 | 2 |
| CLOSPEN2 | test | 0 | 2 | 2 |
| CLOSPEN3 | test | 35 | 1 | 36 |
| CLOSPEN4 | test | 0 | 1 | 1 |
| CLOSPEN5 | test | 15 | 1 | 16 |
| CLOSPEN6 | train | 30 | 0 | 30 |
| GRVAGE1 | test | 0 | 2 | 2 |
| GRVAGE2 | train | 28 | 0 | 28 |
| INTCOMP1 | dev | 18 | 0 | 18 |
| KYCSCHED1 | test | 20 | 1 | 21 |
| KYCSCHED2 | dev | 32 | 0 | 32 |
| KYCSYNC1 | test | 0 | 2 | 2 |
| KYCSYNC2 | test | 41 | 1 | 42 |
| KYCSYNC3 | train | 19 | 0 | 19 |
| LATEFEE1 | test | 15 | 1 | 16 |
| LATEFEE2 | train | 27 | 0 | 27 |
| NOTICE1 | dev | 32 | 0 | 32 |
| OVRLIM1 | train | 12 | 0 | 12 |
| REFADJ1 | train | 31 | 0 | 31 |
| REFADJ2 | test | 12 | 0 | 12 |
| TRNVAL1 | test | 8 | 0 | 8 |
| UNSOLIC1 | train | 32 | 0 | 32 |
