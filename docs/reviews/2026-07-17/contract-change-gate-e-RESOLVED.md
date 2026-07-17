# CONTRACT CHANGE — Gate E threat-model split (RATIFIED)

**Date:** 2026-07-17  
**Decision:** Track C ratifies; Track B signs  
**Contract:** v1.2 → v1.3  
**Backlog:** BL-14

## Ruling

Track C adopts Track B's proposed split without relaxing either threat model:

- The artifact-only hard gate uses only `literal_roundness`, the registered
  feature computable from the shipped artifact. Its deterministic bootstrap
  95% AUC confidence interval must include 0.5.
- The aggregate six-feature probe assumes access to seed bases. Its AUC and
  interval are recorded rather than forced to chance, and the classifier is a
  mandatory seventh baseline in T5.3. T5.3 predeclares the required winning
  margin; headline results report the paired delta and bootstrap interval.

The build manifest and Gate E test carry the same definition, so the gate and
its contract cannot silently diverge.

## Blast radius

- Track B: benchmark manifest and Gate E build test.
- Track C: T5.3 baseline suite and headline comparison reporting.
- Track A: no implementation change; FYI because CONTRACT.md is cross-track.
