# Benchmark v1-pre Distribution

Deterministic seed: `2600`. Target ratios: train 70%, dev 15%, test 15%.
Base-program grouping and real-curated test reservation are hard constraints;
`CI-fragile` marks every split × class × stratum cell with n < 10.

**Constraint warning:** dev is empty because real-curated test reservation consumes every synthetic base except one; splitting that remaining base would leak program identity.

## Split summary

| split | total | synthetic | real_curated | local | interprocedural | base groups |
|---|---:|---:|---:|---:|---:|---:|
| train | 30 | 30 | 0 | 0 | 30 | 1 |
| dev | 0 | 0 | 0 | 0 | 0 | 0 |
| test | 293 | 272 | 21 | 289 | 4 | 14 |

## Split × class × stratum cells

| split | class | stratum | n | CI status |
|---|---|---|---:|---|
| train | D1_stale_threshold | local | 0 | CI-fragile |
| train | D1_stale_threshold | interprocedural | 0 | CI-fragile |
| train | D2_missing_rule | local | 0 | CI-fragile |
| train | D2_missing_rule | interprocedural | 0 | CI-fragile |
| train | D3_contradictory | local | 0 | CI-fragile |
| train | D3_contradictory | interprocedural | 30 | ok |
| train | D4_stale_reference_data | local | 0 | CI-fragile |
| train | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| train | D5_boundary_error | local | 0 | CI-fragile |
| train | D5_boundary_error | interprocedural | 0 | CI-fragile |
| train | D6_dead_code | local | 0 | CI-fragile |
| train | D6_dead_code | interprocedural | 0 | CI-fragile |
| train | D7_conformant | local | 0 | CI-fragile |
| train | D7_conformant | interprocedural | 0 | CI-fragile |
| dev | D1_stale_threshold | local | 0 | CI-fragile |
| dev | D1_stale_threshold | interprocedural | 0 | CI-fragile |
| dev | D2_missing_rule | local | 0 | CI-fragile |
| dev | D2_missing_rule | interprocedural | 0 | CI-fragile |
| dev | D3_contradictory | local | 0 | CI-fragile |
| dev | D3_contradictory | interprocedural | 0 | CI-fragile |
| dev | D4_stale_reference_data | local | 0 | CI-fragile |
| dev | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| dev | D5_boundary_error | local | 0 | CI-fragile |
| dev | D5_boundary_error | interprocedural | 0 | CI-fragile |
| dev | D6_dead_code | local | 0 | CI-fragile |
| dev | D6_dead_code | interprocedural | 0 | CI-fragile |
| dev | D7_conformant | local | 0 | CI-fragile |
| dev | D7_conformant | interprocedural | 0 | CI-fragile |
| test | D1_stale_threshold | local | 95 | ok |
| test | D1_stale_threshold | interprocedural | 1 | CI-fragile |
| test | D2_missing_rule | local | 23 | ok |
| test | D2_missing_rule | interprocedural | 1 | CI-fragile |
| test | D3_contradictory | local | 2 | CI-fragile |
| test | D3_contradictory | interprocedural | 0 | CI-fragile |
| test | D4_stale_reference_data | local | 18 | ok |
| test | D4_stale_reference_data | interprocedural | 0 | CI-fragile |
| test | D5_boundary_error | local | 21 | ok |
| test | D5_boundary_error | interprocedural | 0 | CI-fragile |
| test | D6_dead_code | local | 20 | ok |
| test | D6_dead_code | interprocedural | 1 | CI-fragile |
| test | D7_conformant | local | 110 | ok |
| test | D7_conformant | interprocedural | 1 | CI-fragile |

## Base-program assignment

| base group | split | synthetic | real_curated | total |
|---|---|---:|---:|---:|
| BOIDENT1 | test | 0 | 2 | 2 |
| BOIDENT2 | test | 57 | 1 | 58 |
| CBACT04C | test | 0 | 1 | 1 |
| CBTRN02C | test | 0 | 3 | 3 |
| CLOSPEN1 | test | 0 | 2 | 2 |
| CLOSPEN2 | test | 0 | 2 | 2 |
| CLOSPEN3 | test | 66 | 1 | 67 |
| CLOSPEN4 | test | 0 | 1 | 1 |
| CLOSPEN5 | test | 20 | 1 | 21 |
| GRVAGE1 | test | 0 | 2 | 2 |
| KYCSCHED1 | test | 55 | 1 | 56 |
| KYCSYNC1 | test | 0 | 2 | 2 |
| KYCSYNC2 | test | 73 | 1 | 74 |
| LATEFEE1 | test | 1 | 1 | 2 |
| OVRLIM1 | train | 30 | 0 | 30 |
