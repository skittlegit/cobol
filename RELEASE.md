# Release notes

This release packages the frozen benchmark and local COBOL analysis tools.
It does not establish a deployable regulation-drift detector or end-to-end
automatic regulatory migration.

The frozen benchmark has 307 train, 102 development and 196 test rows,
including 43 resolved real-curated test rows out of 51 candidates. Eight
candidates are excluded. The historical temporal evaluation contains nine
intact pairs. The later independently recorded temporal review roster contains
20 pairs; it is additive evidence and does not replace the historical denominator.
Annotation provenance is human-primary with Claude verification, as documented
in ANNOTATION.md. The separately authorized migration reviews are AI-primary
with independent AI verification and adjudication; they are not human attestations.

Benchmark rows contain gold labels, evidence, and mutation metadata. A raw
`DriftInstance` is unsuitable as detector input. Reproduction must use the
gold-hidden request construction and leakage checks documented in the evaluation
work orders. Training, development and test source groups remain disjoint.

Historical M4 remains NO_GO. The completed historical M5 report preserves the
agent's measured underperformance on the interprocedural stratum and its failed
contract bars. The surface attacker is null anti-gaming evidence; its vacated
performance floor is not a release gate. Configuration 3 remains an archived
readiness failure. Configuration 4 is NOT_EVALUABLE because required signed
references fail provenance checks despite valid host replay. Its descriptive
balanced accuracy, paired significance and temporal quality gates also fail.
The repeated hidden-roster follow-up is not a first-look estimate. These four
configuration lineages must remain separately identified.

Migration is limited to the exact separately reviewed oracle-assisted roster.
Detector-led generation has no eligible cases. Oracle-assisted results are an
upper bound, share source-bundle dependence, and cannot establish detector
utility, universal compliance, semantic equivalence or untested host behavior.
The terminal migration report records four official oracle-assisted patch
successes across three source bundles, zero failures and zero abstentions,
with zero eligible detector-led cases. All four patched cases passed real WSL
compilation and finite intended/regression checks. They cover dependent D1
interprocedural cases, a D4 case and a D5 case; they are not an independent
random sample of production changes. The separate transport qualification
contributes no official result. Provider resource telemetry is not_recorded.
Actual standalone and Linux non-root/network-none/read-only container qualification
pass, including local neural retrieval and finite batch compilation/execution.
CICS execution remains unavailable. Final archive and paper readiness is
established by separately published measured receipts for the exact source
revision. The source archive's draft paper and a subsequently bound final
submission package are distinct artifacts.

Code is MIT licensed. CardDemo-derived material retains Apache-2.0 licensing
and attribution in release/licenses/. Regulation metadata identifies source
documents; inclusion of metadata does not grant redistribution rights in those
documents. Fetched corpora, regulation PDFs, local model caches, credentials,
chat history and raw provider logs are excluded from the reproducibility archive.
Operators supply their own authorized corpus and read-only copybook mounts.

The standalone deployment guide is docs/DEPLOYMENT.md. The qualified Linux
profile is deploy/LINUX.md and deploy/container_smoke.py; its `/tmp` mount must
include `exec` for the locally compiled grammar library and batch binaries.
The generic container example in the sealed standalone guide predates this
qualification and needs that explicit mount option. Reproducibility commands
are in docs/REPRODUCIBILITY.md. Final readiness is determined by their measured
qualification receipts, the exact release manifest and the closed release
addendum. UI/T7.4 remains deferred. Remote and multi-tenant security are outside
the supplied stdio profile.
