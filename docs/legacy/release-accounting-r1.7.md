# Release accounting

R1.7 explicitly accounts for T7.2 and T7.3 without closing them. The detector
evaluation reports and frozen decision are evaluation deliverables; the on-prem
deployment bundle and deterministic release archive remain separate work.
UI/T7.4 remains deferred. M7 is not complete.

| Task | Accounted state | Existing evidence | Remaining gates |
|---|---|---|---|
| T7.2 | NOT_COMPLETE | Wheel asset regression tests and T7.1 stdio MCP implementation record | Offline payload manifest, installer, staged wheelhouse/model cache, non-root container, deployment guide, clean/network-disabled smoke, missing-payload/checksum tests, complete deployment gates |
| T7.3 | NOT_COMPLETE | Frozen benchmark and historical T5.5/M5 analysis | Deterministic release builder, licensed path/size/hash manifest, release notes including successor results, exact-count/gold-hidden-input explanation, two clean identical builds, unpacked validation, release-commit gates |
| T7.4 | DEFERRED | R1 work-order exclusion | No UI work authorized by R1.7 |

The checkout lacks T7.2's canonical `deploy/`, `docs/DEPLOYMENT.md`, and
`tests/test_offline_bundle.py`, and T7.3's `release/manifest.json`, `RELEASE.md`,
and `scripts/build_release.py`. The machine-readable accounting artifact at
`data/eval/m4/release-accounting.json` records these missing paths and pins the
relevant work orders and existing prerequisite evidence by SHA-256.

No deployment, network-disabled clean installation, container build, release
archive build, or release tag was attempted for this accounting. Existing test
source and historical test records are not new execution receipts. Publishing
evaluation evidence to Git does not establish deployment or package readiness.

Historical M5 closure remains preserved. The successor detector/migration
release addendum remains assigned to GOAL-R2. Model-primary T6-v2 review must be
described with its actual provenance; the older T7.3 wording about human-primary
annotation does not authorize relabeling model reviews as human reviews.

R1.7 performance reporting must also retain operational limits: in-product
provider tokens, turns, timing, cache telemetry, and metered billing are not
recorded in the completed run. Tool event evidence may support measured host
observations and tool counts, but does not establish end-to-end deployment
latency, an offline bundle, or a dollar-cost estimate. Measured quality failures,
signed-reference discrepancies, and interrupted/rejected attempts remain in
their sealed evaluation lineage.
