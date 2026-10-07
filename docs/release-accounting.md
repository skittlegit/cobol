# Release accounting

The applicable R2.1-R2.9 migration work is terminal. Four official oracle-assisted
patches pass real WSL validation across three distinct source bundles; detector-led
migration remains inactive. Historical M4/M5 decisions and configuration-4
NOT_EVALUABLE provenance are preserved. R2.10 and M7 remain incomplete.

| Task | Current state | Measured evidence | Remaining gates |
| --- | --- | --- | --- |
| T7.2 | COMPLETE; standalone and Linux container pass | Clean Python 3.12 installation from 70 local hash-locked packages; actual eleven-tool neural stdio smoke; deploy/qualification/receipt.json | None; actual non-root/network-none/read-only application qualification retained in deploy/qualification/container-terminal-receipt.json |
| T7.3 | Licensed deterministic builder prepared | Strict benchmark/successor allowlist, hash/count/schema gates, outside-tree verification tests | Two actual clean builds, retained manifest/archive receipts, final source commit and unpacked wheel validation |
| T7.5 | Numeric draft prepared | Generated paper and JSON-pointer number audit; negative results preserved | Final deployment/release/source-commit/benchmark bindings and final anonymous submission package |
| T7.4 | DEFERRED | Work-order exclusion | No UI work is included in R2 |

The earlier R1.7 accounting is retained in
[legacy/release-accounting-r1.7.md](legacy/release-accounting-r1.7.md).
Its machine artifact at data/eval/m4/release-accounting.json remains historical;
its former missing-path claims describe that checkpoint, not the current tree.

Global Ruff lint checks active code. Raw execution-evidence trees retain their
exact bytes and are excluded from active lint discovery. The repository-wide
formatter finds inherited style differences, including immutable runtime files;
that diagnostic is retained without rewriting any of the 120 frozen runtime
sources. Formatting checks apply to newly changed unfrozen implementations.
CI and final release gates still require full offline tests, Ruff lint, clean
diffs, annotation/freeze validation and packaging verification. A passing benchmark
archive does not establish an offline deployment or final paper submission.
