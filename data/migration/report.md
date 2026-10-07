# Migration report

Passed 4, failed 0, not run 0 of 4 cases.

| case | finding | class | interprocedural | outcome | checks | failed checks |
| --- | --- | --- | --- | --- | --- | --- |
| migration_075075 | oracle | D1_stale_threshold | yes | pass | 8 | - |
| migration_191889 | oracle | D4_stale_reference_data | no | pass | 8 | - |
| migration_255807 | oracle | D1_stale_threshold | yes | pass | 8 | - |
| migration_345332 | oracle | D5_boundary_error | no | pass | 8 | - |

Validation applies each patch, checks the edit scope, compiles every host program with GnuCOBOL 3.2.0, checks source assertions, confirms the intended fixtures fail before the patch, and runs every fixture after it. This is finite fixture-level evidence, not proof of program equivalence.
