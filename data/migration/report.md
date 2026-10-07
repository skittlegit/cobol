# Migration results

Detector-led migration is inactive: configuration 4 is NOT_EVALUABLE.
Oracle-assisted results are an upper bound and do not establish end-to-end detector utility.

| Track | Eligible | Evaluated | Pass | Fail | Abstain |
| --- | ---: | ---: | ---: | ---: | ---: |
| detector_led | 0 | 0 | 0 | 0 | 0 |
| oracle_assisted | 4 | 4 | 4 | 0 | 0 |

Provider tokens, turns and latency: `not_recorded`.

Machine report SHA-256: `184993d1b9732ad67562926b641684c19095440d6d14ab15df862cd4bae18f17`.

Qualification results are excluded from every official denominator.

- all_failed_patches_abstentions_unavailable_checks_and_infrastructure_failures_remain_visible
- dependent_source_cases_are_not_independent_contributions
- finite_fixtures_do_not_prove_complete_equivalence_or_universal_compliance
- no_untested_host_fanout_claim

The 4 oracle-assisted cases cover 3 distinct source bundles.
The two D1 interprocedural cutoff cases share a source bundle; their successes are dependent.
No independent-case confidence interval or universal compliance claim is supported.

| Validation category | Pass | Applicable | Not applicable |
| --- | ---: | ---: | ---: |
| apply | 4 | 4 | 0 |
| compile | 4 | 4 | 0 |
| fanout | 3 | 3 | 1 |
| intended | 4 | 4 | 0 |
| parser | 4 | 4 | 0 |
| regressions | 4 | 4 | 0 |
| scope | 4 | 4 | 0 |
| source_binding | 4 | 4 | 0 |
| static_consistency | 4 | 4 | 0 |

Class, stratum and capability outcomes are generated from the exact case records:

- by_drift_type: `{"D1_stale_threshold": {"pass": 2}, "D4_stale_reference_data": {"pass": 1}, "D5_boundary_error": {"pass": 1}}`
- by_stratum: `{"interprocedural": {"pass": 2}, "local": {"pass": 2}}`
- by_capability: `{"batch_executable": {"pass": 1}, "copybook_fanout": {"pass": 3}}`

Measured successes are restricted to the authorized finite fixtures:

- migration_075075: pass; 1 changed line(s), precision 1.0, unrelated changes 0.
- migration_255807: pass; 1 changed line(s), precision 1.0, unrelated changes 0.
- migration_191889: pass; 1 changed line(s), precision 1.0, unrelated changes 0.
- migration_345332: pass; 1 changed line(s), precision 1.0, unrelated changes 0.

No failed patch or abstention was observed in this roster. This does not estimate reliability outside these selected cases.
Compiler, intended and regression results reflect actual patched-source WSL execution; finite static consistency is not semantic equivalence.
