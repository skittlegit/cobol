# GOAL-R2 work order - migration evaluation and release close

**Owners:** Track A / Track C
**State:** blocked until GOAL-R1 freezes one detector decision and roster
**Windowing:** run one numbered section per Codex five-hour window
**Depends on:** GOAL-R1, promoted T6-v2, and the existing offline migration gates
**Excludes:** UI/T7.4

## Required outcome

Run the isolated migration agent, validate every generated patch, publish
separate detector-led and oracle-assisted results, and publish the successor
release addendum without erasing the closed T5.5/M5 or prior M4 evidence.

## Five-hour execution contract

Each section targets 4 hours 15 minutes of execution and reserves 45 minutes
for sealing, deterministic checks, reports, and a clean handoff. At 4:15, stop
launching new provider tasks and close the current checkpoint. If a section is
not terminal, resume that same section in the next five-hour window.

Use at most three isolated Luna/max tasks concurrently. Checkpoint every case.
Self-heal staging, schema, hash, apply, validator, replay, and report defects
within the same section before marking it complete. Do not manually improve a
model patch, erase a failed patch or abstention, pool detector and oracle
tracks, fabricate compiler/provider evidence, or weaken safety gates.

Use this prompt for each window:

> Execute only section R2.N from
> `docs/tasks/GOAL-R2-work-order.md`. Resume its durable checkpoint, use up to
> three isolated Luna/max workers, self-heal permitted failures, update project
> records, and stop at that section's terminal handoff. Do not start R2.N+1.

## R2.1 - freeze rosters, runtime, and requests

**Budget:** <= 5 hours.

1. Validate GOAL-R1's frozen detector decision and its exact eligible findings.
2. Validate the promoted T6-v2 20-pair / 40-side manifest and migration runtime
   snapshot.
3. Freeze two non-pooled rosters: detector-led verified findings and
   oracle-assisted frozen findings.
4. Materialize one-case Luna/max requests with only authorized source,
   verified finding, patch scope, and output contract.
5. Prove source, request, staging, schema, runtime, validator, and run-key
   binding with provider-free tests and one isolated qualification.

**Handoff:** immutable rosters and requests, exact denominators, zero hidden
cross-track leakage, and green preflight tests.

## R2.2 - T6.2 migration generation, first half

**Budget:** <= 5 hours. **Depends on:** R2.1.

1. Execute the first deterministic half of each frozen roster, keeping tracks
   separately labeled.
2. Each case ends in one exact sealed patch proposal or explicit abstention.
3. Preserve request/final hashes, events, tool logs, unavailable telemetry,
   interruptions, and resume evidence.
4. Isolate malformed finals under diagnostic identities and retry unchanged
   requests without counting an unvalidated replacement.

**Handoff:** all first-half run keys terminal and replayable, with no broken
staging state.

## R2.3 - T6.2 migration generation, second half

**Budget:** <= 5 hours. **Depends on:** R2.2.

1. Resume the same frozen run and process every remaining run key.
2. Reconcile proposals, abstentions, malformed attempts, interruptions, and
   exact eligible/evaluated denominators for both tracks.
3. Freeze the complete T6.2 generation ledger. Do not advance with pending keys.

**Handoff:** complete sealed patch/abstention coverage and one immutable
validation input roster.

## R2.4 - T6.3 validation, first half

**Budget:** <= 5 hours. **Depends on:** R2.3.

1. Apply proposals only to disposable per-case staging copies.
2. Validate the first deterministic half for patch scope, clean application,
   parser integrity, call graph/dataflow/slice consistency, intended behavior,
   unaffected regressions, copybook fan-out, and source-hash binding.
3. Use pinned GnuCOBOL compile/execution for supported batch cases when the
   authorized runtime provides it. Record unavailable compiler/CICS capability;
   never convert it to a pass.
4. A failed generated patch remains a measured failure.

**Handoff:** first-half terminal validation records, reproducible staging, and
green validator/integrity tests.

## R2.5 - finish validation and publish T6.4

**Budget:** <= 5 hours. **Depends on:** R2.4.

1. Validate every remaining proposal under the identical frozen validator.
2. Reach terminal verdicts for all proposals and abstentions.
3. Build T6.4 with exact patch, abstention, apply, parse, compile,
   intended-test, regression, affected-line, class, stratum, and capability
   results.
4. Keep detector-led and oracle-assisted results separate in every table and
   narrative. Re-hash claims to machine evidence and report unavailable Luna
   telemetry as `not_recorded`.

**Handoff:** reconciled `data/migration/report.json` and
`data/migration/report.md` with no pending validation state.

## R2.6 - successor release addendum and close

**Budget:** <= 5 hours. **Depends on:** R2.5.

1. Consume the closed T5.5/T5.5A evidence and complete the successor release
   addendum and T7.5 from the frozen detector and migration decisions.
2. Preserve configurations 1-4 as distinct auditable evidence.
3. Update `DATASHEET.md`, `STATUS.md`, `FLAGS.md`, and the final release
   record; keep UI/T7.4 explicitly deferred.
4. Apply the repository naming rule: current human-facing outputs are
   unversioned; superseded human-facing outputs move under `legacy/`;
   hash-bound protocol identities remain immutable and are selected by an
   unversioned manifest/dashboard.
5. Run focused and full deterministic tests, Ruff, artifact reconciliation,
   packaging checks, and a clean Git audit.

**Completion:** T6.2-T6.4, the successor addendum, and T7.5 are terminal and
auditable; reports and manifests reconcile; every active non-UI flag is cleared
or terminal; and the release record states exactly what is and is not supported.

## Naming and legacy rule

Completed artifacts and human-facing outputs use unversioned filesystem names.
An in-progress hash-bound execution tree may keep its frozen name only until
its terminal promotion step. Before replacement, move superseded evidence
under the nearest `legacy/` directory. Protocol and schema version values
embedded inside sealed records remain unchanged because they identify formats.
