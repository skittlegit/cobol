# GOAL-R2 work order - migration evaluation and release close

**Owners:** Track A / Track C
**State:** authorized; R1.7 input frozen, R2.1 review/fixture preparation next
**Windowing:** ten planned Codex five-hour windows at the 24-task planning
ceiling; eight when only one 12-case track is eligible
**Depends on:** GOAL-R1, promoted T6-v2, and the existing offline migration gates
**Excludes:** UI/T7.4

**Model decision (2026-09-23):** R2 migration generation uses
`gpt-6-luna` at `max` reasoning. R1's active frozen evaluation continues with
`gpt-5.6-luna`/`max`; completed T6 reviews retain their recorded identities.
R2.2 must bind the new model to its fresh requests and qualification before
live generation. This decision does not reopen R1 or historical evidence.

**2026-10-06 input and review amendment:** R1.7 is complete. Consume
`data/eval/m4/evaluation-manifest.json`, `detector-decision.json`, and
`r2-input-roster.json` with their exact hashes. The configuration-4 detector is
NOT_EVALUABLE for required signed-reference provenance, while measured quality
failures remain descriptive. Detector-led generation is inactive (zero findings).
The 12 oracle-assisted candidates are not reviewed migration cases yet.

The user explicitly authorized AI-primary migration review with independent AI
verification and adjudication. Implement a separate, additive non-human protocol
and loader; preserve the existing human contracts and candidate records. Fresh
reviews must examine the actual migration case, allowed scopes, intended behavior,
unaffected regressions, and concrete fixtures. T6-v2 temporal reviews cannot
substitute for these migration reviews. Justify the three repeated-source pairs
before promotion. Freeze a real parser/static/compiler/behavior validation backend;
stub-backed unit tests do not establish live validation capability. See
`docs/tasks/R2-review-design.md` for preparation design.

A persistent goal now authorizes continued sequential work through all applicable
R2 sections. Keep checkpoints across limits and resume the same unfinished
section; no completed provider key may be rerun. This goal does not guarantee a
specific quota-reset wake-up time or override actual provider availability.

## Required outcome

Run the isolated migration agent, validate every generated patch, publish
separate detector-led and oracle-assisted results, and publish the successor
release addendum without erasing the closed T5.5/M5 or prior M4 evidence.

## Five-hour execution contract

Each section is one real five-hour window: at most 4 hours 15 minutes of work
and at least 45 minutes for sealing, replay, tests, documentation, and handoff.
At 4:15, stop launching provider work. An unfinished wave resumes under the
same section identifier in an explicitly recorded repair window; it never
silently consumes the next section.

The planning denominator is concrete. The current migration candidate roster
contains 12 cases. R2 may freeze at most two non-pooled tracks, so the planning
ceiling is 24 isolated GPT-6 Luna/max generation tasks. R2.1 must replace this ceiling
with the exact frozen denominator before any provider call. If that denominator
exceeds 24, recompute and publish the window count instead of retaining this
schedule.

The live-generation cap is six terminal run keys per window: at most two tasks
per worker across three isolated workers. This is deliberately below the
theoretical concurrency maximum because migration tasks create patches and
staging evidence and may require an unchanged-request infrastructure retry.
The validation cap is eight terminal records per window. These caps are
planning limits, not permission to stop early when safe capacity remains.

At the 24-task ceiling the baseline plan is **10 windows / 50 hours**:

- 2 preparation/freeze windows;
- 4 generation windows of at most 6 live tasks;
- 3 validation/report windows of at most 8 records; and
- 1 release-close window.

If only the 12-case oracle-assisted track is eligible, generation waves R2.5
and R2.6 are skipped after reconciliation, producing **8 windows / 40 hours**.
Each genuine repair window adds five hours and must name its exact unresolved
keys. These are planning ceilings, not promises that a provider or compiler
failure will fit inside the original window.

Use at most three isolated GPT-6 Luna/max tasks concurrently. Checkpoint every case.
Self-heal staging, schema, hash, apply, validator, replay, and report defects
within the same section before marking it complete. Do not manually improve a
model patch, erase a failed patch or abstention, pool detector and oracle
tracks, fabricate compiler/provider evidence, or weaken safety gates.

Use this prompt for each window:

> Execute only section R2.N from
> `docs/tasks/GOAL-R2-work-order.md`. Resume its durable checkpoint, use up to
> three isolated GPT-6 Luna/max workers, self-heal permitted failures, update project
> records, and stop at that section's terminal handoff. Do not start R2.N+1.

## R2.1 - freeze exact rosters and planning denominator

**Budget:** <= 5 hours.

1. Validate GOAL-R1's frozen detector decision and exact eligible findings.
2. Validate the promoted T6-v2 20-pair / 40-side manifest and migration runtime
   snapshot.
3. Freeze the detector-led and oracle-assisted rosters separately.
4. Publish exact per-track and combined generation denominators.
5. Recalculate the numbered generation and validation waves if the combined
   denominator is not 12 or 24.

**Handoff:** immutable rosters, exact denominators, a deterministic wave map,
and zero hidden cross-track leakage.

## R2.2 - freeze runtime, requests, and qualification

**Budget:** <= 5 hours. **Depends on:** R2.1.

1. Materialize one-case `gpt-6-luna`/`max` requests containing only authorized source,
   verified finding, patch scope, and output contract.
2. Freeze source, request, staging, schema, runtime, validator, and run-key
   bindings.
3. Run provider-free tests and one isolated qualification task.
4. Repair request/capture/staging defects now; do not discover them across the
   live roster.

**Handoff:** immutable requests and runtime identity, green preflight, and one
sealed/replay-valid qualification that is not counted in the live denominator.

## R2.3 - T6.2 generation wave 1

**Budget:** <= 5 hours. **Depends on:** R2.2.

1. Execute deterministic generation keys 1-6 across the frozen non-pooled
   rosters, using at most three isolated workers.
2. Seal one exact patch proposal or explicit abstention per key.
3. Preserve request/final hashes, events, tool logs, interruptions, and resume
   evidence. Unchanged-request infrastructure retries remain uncounted until
   sealed.

**Handoff:** six or fewer wave-1 keys terminal and replay-valid; no pending key
is misreported as completed.

## R2.4 - T6.2 generation wave 2

**Budget:** <= 5 hours. **Depends on:** R2.3.

Process deterministic generation keys 7-12 under the identical contracts and
produce the same terminal, replay-valid handoff. If the full denominator is 12,
reconcile and freeze the T6.2 generation ledger here, then skip R2.5-R2.6.

## R2.5 - T6.2 generation wave 3 (conditional)

**Budget:** <= 5 hours. **Depends on:** R2.4. **Required only when denominator > 12.**

Process deterministic generation keys 13-18 under the identical contracts.

## R2.6 - finish T6.2 generation and reconcile

**Budget:** <= 5 hours. **Depends on:** R2.5 when required, otherwise R2.4.

1. Process deterministic generation keys 19-24, or every remaining key when
   the exact denominator is smaller.
2. Reconcile proposals, abstentions, malformed attempts, interruptions, and
   per-track denominators.
3. Freeze the complete T6.2 ledger and immutable validation roster. Do not
   advance with pending keys.

**Handoff:** complete sealed patch/abstention coverage and one immutable
validation input roster.

## R2.7 - T6.3 validation wave 1

**Budget:** <= 5 hours. **Depends on:** terminal T6.2 generation.

1. Apply proposals only to disposable per-case staging copies.
2. Validate deterministic records 1-8 for patch scope, clean application,
   parser integrity, call graph/dataflow/slice consistency, intended behavior,
   unaffected regressions, copybook fan-out, and source-hash binding.
3. Use pinned GnuCOBOL compile/execution for supported batch cases when the
   authorized runtime provides it. Record unavailable compiler/CICS capability;
   never convert it to a pass.
4. A failed generated patch remains a measured failure.

**Handoff:** up to eight terminal validation records, reproducible staging, and
green validator/integrity tests.

## R2.8 - T6.3 validation wave 2

**Budget:** <= 5 hours. **Depends on:** R2.7.

Validate deterministic records 9-16 with the identical frozen validator and
terminal evidence requirements.

## R2.9 - finish validation and publish T6.4

**Budget:** <= 5 hours. **Depends on:** R2.8.

1. Validate deterministic records 17-24, or every remaining record under the
   identical frozen validator.
2. Reach terminal verdicts for all proposals and abstentions.
3. Build T6.4 with exact patch, abstention, apply, parse, compile,
   intended-test, regression, affected-line, class, stratum, and capability
   results.
4. Keep detector-led and oracle-assisted results separate in every table and
   narrative. Re-hash claims to machine evidence and report unavailable Luna
   telemetry as `not_recorded`.

**Handoff:** reconciled `data/migration/report.json` and
`data/migration/report.md` with no pending validation state.

## R2.10 - successor release addendum and close

**Budget:** <= 5 hours. **Depends on:** R2.9.

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
