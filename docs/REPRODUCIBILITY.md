ï»¿# Reproducing the benchmark release

The release builder packages the frozen v1 benchmark and its locked annotation
chain, project validation source, documentation, license/attribution files and
regulation-source pin metadata. The package does not contain fetched corpora,
model caches, credentials, RBI PDF payloads, provider logs or superseded splits.
`release/manifest.json` records the clean Git revision, every payload path, size,
SHA-256, role and license, and the frozen benchmark manifest hash. It is created
inside the archive and is not a self-hash entry. Archive bytes use sorted paths,
fixed ZIP timestamps/permissions and uncompressed entries.

Use Python 3.12 with the project's declared dependencies already installed.
From a clean committed checkout, choose two output paths outside the checkout:

```powershell
python scripts/build_release.py two-builds --output C:/release-build/one.zip --second-output C:/release-build/two.zip
```

The builder rejects tracked or untracked dirt, missing locked files, stale
counts, schema failures, benchmark/annotation checksum changes, source-group
leakage and Git-versus-working-tree byte discrepancies. Outputs are immutable:
a differing existing archive is refused. Both archives must have identical
bytes. A copied file with converted line endings cannot masquerade as the
recorded commit. Build receipts do not establish full-suite success; record
annotation/freeze gates, packaging checks, `git diff --check` and full offline
tests at the final release revision separately.

Unpack into an empty directory outside the developer checkout. With dependencies
available, validate using only the unpacked source and payload:

```powershell
python -B scripts/build_release.py verify --root C:/release-build/unpacked
```

The validator requires exactly the listed files plus its manifest. It re-hashes
sizes, content and licensing metadata, revalidates each `DriftInstance`, the
freeze manifest and all four typed annotation files, recomputes 307 train,
102 dev, 196 test, 43 real-curated test rows, nine historical T6 pairs and eight
excluded IDs, and checks source-group separation. Do not install an editable
copy into the unpacked directory before verification: generated package metadata
is an unexpected file. Dependency installation can use the separate deployment
bundle; archive validation itself needs no provider or network access.

Raw benchmark rows contain gold: `drift_type`, `target_path`, `labels`,
`gold_rationale`, mutation metadata and annotator notes must not reach a detector.
Create detector input from the authorized regulation clause and authorized source
bundle, deriving program identity from its source. `code_locus` and gold labels
are oracle coordinates; any oracle slice must be explicitly designated as
oracle-assisted. Raw `DriftInstance` JSON is not a safe detector prompt.

Historical human-primary/Claude-verification evidence retains its original
identity. Additive T6-v2 and migration AI reviews do not become human reviews.
The historical nine-pair limitation, M4 NO_GO, poor M5 quality, configuration-4
NOT_EVALUABLE signed-reference decision and unavailable provider usage telemetry
remain preserved. Successor migration conclusions come from the separate terminal
migration report and release notes; validating benchmark bytes does not establish
successful remediation or detector eligibility. UI/T7.4 remains deferred.

This guide and passing builder tests are preparation evidence. T7.3 completion
requires actual two clean release builds, retained receipts, unpacked validation,
release notes with measured successor results, and checks at the final commit.

The final successor addendum uses `--profile successor`. This requires exactly
seven sanitized public copies under `release/public/`: `migration-report.json`,
`migration-report.md`, `m4-report.json`, `detector-decision.json`, `m5-report.json`,
`paper.md` and `paper-numbers.json`. Raw migration validation receipts are not
allowlisted because they can contain local compiler paths. JSON summaries use
an exact envelope with `schema_version: public-release-summary-v1`, a lowercase
64-character `source_sha256`, and a dictionary `content`. Markdown summaries
carry the same version and source hash as plain metadata lines. Absolute Windows
and common Unix host paths are rejected. Source hashes bind each sanitized copy
to its canonical input without publishing local paths. Terminal reconciliation
and report-number validation remain required before generating these copies;
passing envelope/hash syntax does not establish that a report's claims are true.
The benchmark profile does not satisfy final successor addendum completion.

The source archive also includes the canonical `MANIFEST.in` and
`data/regulations/clauses.jsonl`, required by the shipped wheel build hook.
Every clause is validated with the current `RegulationClause` model; record IDs
must be nonempty and unique. The manifest labels these quoted clauses as
`external-RBI-source-terms`, with no MIT redistribution grant. The canonical
source README requires: "Re-pinning a file whose bytes changed is a hard error
(provenance break)." Its provenance restrictions do not grant copyright rights.
The existing datasheet describes quoted text as research/citation material and
requires consulting the authoritative RBI publication. PDF payloads remain
excluded. This profile does not claim complete primary-document availability.

After archive verification, a wheel can be built entirely from the unpacked
source with already staged build dependencies and no package-index access:

```powershell
$env:PIP_NO_INDEX = '1'
python -m build --no-isolation --wheel --outdir C:/release-build/wheel
```

The wheel retains the exact vendored grammar, regulation clause JSONL and source
pin metadata. Its lack of RBI PDF payloads is deliberate; operator access to
underlying authorized primary documents and deployment model payloads is a
separate requirement. A successful wheel build does not establish the complete
T7.2 container or retrieval qualification. Run the archive verifier before
building, because wheel construction creates files outside its initial allowlist.

## Completed source revision

The measured successor archive is `release/cobol-source.zip`, built twice from
clean source commit `8565cd36e7630ae3452191fd48d06fd5ebd39b39`. To reproduce those
exact bytes, use that commit in a separate clean checkout and `--profile successor`,
with outputs outside the checkout. `release/two-builds.json`,
`release/unpacked-validation.json` and `release/wheel-validation.json` retain
the actual results. A later publication commit adds the final paper and receipts;
its final paper is distinct from the draft public paper inside the source archive.
The frozen benchmark manifest is identical in both artifact revisions.
