# Anonymous submission artifacts

Build with `python scripts/build_paper.py --binding paper/finalization-binding.json`;
verify with the same command plus `--check`. Neither command calls a provider.
The generated `manuscript.md`, `manuscript.html`, `numbers.md`, and
`claim-map.json` are deterministic. The numerical appendix includes the full
frozen results, including failed bars and supplemental measurements.

The current manuscript is SUBMISSION_READY. Its explicit binding pins actual
passed deployment, two clean identical source archives, outside-tree validation
and the terminal migration report to source commit
`8565cd36e7630ae3452191fd48d06fd5ebd39b39` and the frozen benchmark manifest.
Readiness is measured by these receipts, not inferred from this directory.
The anonymous document package is separate from the attributed software archive;
it contains no software code or copyright-owner identity. Its local LICENSE file
is a review notice, not a replacement software license. The separately distributed
source archive retains the original MIT and Apache notices.

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
