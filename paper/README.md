# Anonymous paper draft

Build with `python scripts/build_paper.py`; verify with
`python scripts/build_paper.py --check`. Neither command calls a provider.
The generated `manuscript.md`, `manuscript.html`, `numbers.md`, and
`claim-map.json` are deterministic. The numerical appendix includes the full
frozen results, including failed bars and supplemental measurements.

This is a draft. Final submission must bind the completed deployment and
release validation to the same source commit and benchmark manifest. It must
also incorporate the terminal migration report. Those gates are intentionally
not inferred from the existence of this directory.

Finalization uses an explicit `--binding paper/finalization-binding.json`.
The `paper-finalization-binding-v1` object has exactly these fields:
`schema_version`, `source_commit`, `benchmark_manifest`, `migration_report`,
`release_manifest`, `release_two_builds`, `release_unpacked_validation`, and
`deployment_receipt`. Every artifact field is a `{path, sha256}` raw-byte pin
to a checkout-relative JSON file. The source commit is the actual archive's
commit, supplied separately; the builder never infers a self-referential
commit from its own generated files.

The migration report must have schema `migration-stage-report-v1` and status
`COMPLETE`. The release manifest must have schema
`licensed-benchmark-release-v1`; its commit and benchmark identity must match
the explicit binding, and its profile must be `successor`. The two-build receipt
must be `IDENTICAL` with matching archive hashes, and unpacked validation must
be `VALID` at that same commit and explicitly identify that same archive hash.
Deployment requires status `PASS`, `container_execution: PASS`, verified OS
network isolation, an explicit `source_commit`, and current deployment source
pins. Its `measured_receipt: {path, sha256}` must pin retained measurement with
those same passed container/isolation states. Each deployment source pin must
match a blob at the archive source commit when Git is available, or a matching
file hash in the validated archive manifest otherwise. Standalone success
with unavailable container execution remains a draft. Missing or incomplete
success gates also remain a draft; stale pins and identity substitutions fail.

When present, `data/migration/report.json` contributes numeric measurements
and explicit result qualifiers to the source-bound appendix, including an
inactive detector denominator. Raw validation logs and backend paths are
excluded. The root coordinator owns the public release wrappers and final
source binding; creating the draft does not complete those release gates.
The archive source revision and a later finalized paper artifact revision are
distinct. The final generated paper is not claimed byte-identical to the draft
paper inside the earlier validated archive.
