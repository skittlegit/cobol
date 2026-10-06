# GOAL-R1 work order - finish detector evaluation

**Owner:** Track C
**State:** COMPLETE; GPT-6 Luna follow-up R1.5-R1.7 terminal
**Windowing:** run one numbered section per Codex five-hour window
**Depends on:** immutable configuration-3 smoke evidence and promoted T6-v2
**Excludes:** UI/T7.4 and all GOAL-R2 migration work

## Required outcome

Finish the configuration-4 adaptive train/dev qualification, freeze the
successful method, pass a fresh all-six-system smoke, execute the still-unread
hidden test exactly once, and publish T8.3/T8.4 with one auditable detector
decision.

## Starting checkpoint

Do not repeat completed work.

The original configuration-4 requests and R1.4 smoke/full-run freeze use
`gpt-5.6-luna` at `max` reasoning. That lineage is preserved at 78/305 sealed
R1.5 first-half tasks. The 2026-09-23 user-directed GPT-6 Luna repeat below
has a separate predeclared lineage and does not relabel or replace those keys.
Its qualification and 44 smoke tasks are sealed and replay valid, with all six
systems `VALID`. The 196-row, 610-task full run is prepared with zero full-run
provider calls at preparation. The user started those frozen tasks on
2026-09-23; checkpoint each sealed result without changing the freeze.
The 2026-10-04 checkpoint is COMPLETE at 305/305 sealed first-half keys,
zero pending runnable keys, and zero terminal contract rejections. Targeted recoveries,
failed attempts, and interrupted sessions retain their original diagnostics.
On 2026-10-03, agent ordinals 85/86 and adaptive ordinal 85 were resumed
from unchanged requests after confirming their earlier sessions had no final.
Their prior tool logs are retained under `rejected-tool-logs` and pinned in
`full/interrupted-attempts.json`.
The 2026-10-03 window was interrupted. Its three unfinished workers have no
final and their tool logs are preserved in `full/interrupted-attempts.json`.
Earlier on 2026-10-04, Windows Application Control blocked two generated
harness executables (14 passed, 2 failed), and fresh worker creation reached
the orchestration thread limit. These historical blockers remain preserved in
`diagnostics/compiler-restoration.json` and
`diagnostics/session-thread-limit.json`. Fresh-session recovery resolved both
blockers, resumed unchanged requests, and sealed adaptive ordinal 91.
Do not reuse a worker from another case.
The earlier session accidentally executed twelve second-half oracle batches
(ordinals 50-61) ahead of the section order; preserve these frozen results.
There are 317/610 sealed tasks overall and 293 immutable keys remaining for
R1.6. R1.5 is complete; no R1.6 work was started in this recovery window.
The coding coordinator changed to `gpt-6.1-sol` on
2026-10-02; evaluator requests remain `gpt-6-luna`/`max`.
Fresh-session recovery on 2026-10-04 restored worker capacity and passed the
unchanged native compiler harness at 16/16 plus compiler policy at 12/12.
All eight remaining first-half keys are now sealed and replay-valid.
The earlier compiler and thread-limit failures remain diagnostic history.
See `diagnostics/fresh-session-resume.json` and `full/r1.5-handoff.json` for
the terminal recovery record and hash-bound handoff. Three invalid adaptive
91 finals remain preserved diagnostics; its new exact final passed schema and
host replay without resetting its bounded tool evidence.

- Configuration-3 `lineage-v4` is immutable historical evidence under
  `data/eval/legacy/m4-config3`: 37/37 tasks and 84/84 evaluations replayed;
  five systems are `VALID`; adaptive is `NOT_EVALUABLE`; no hidden-test row
  was executed.
- T6.1 promotion and both model reviews/adjudication are complete at 20 pairs /
  40 sides. No human-primary review remains a release requirement.
- Configuration-4 infrastructure, materialization, replay, and runner work is
  implemented; the focused provider-free gate was 95 tests plus Ruff.
- The active dev package is
  `data/eval/m4/lineage/train-dev/adaptive_agent`, freeze SHA-256
  `4403a6a0e36534ecc80f533490fe7cb7c3dfb35b8205f619b6efebbb54958729`.
- The 102 signed prompts keep their original tool-command bytes. The host's
  exact frozen-path compatibility mapping redirects only that historical
  staging path to the canonical plain tree; migration replay is 26/26 green.
- Durable replay is 22/102 rows, 80 pending, zero infrastructure failures,
  zero recorded contract rejections, and zero unverified emissions. Provisional
  metrics are F1 0.7826, balanced accuracy 0.4017, answer rate 0.5000, and
  answered accuracy 0.9091.
- Ordinal 11 / `drift_108519` has an unsealed malformed 65-character evidence
  hash and must be retried from its unchanged frozen request. The later
  quota-limited attempt produced no countable result.
- The most recent provider response reported the restored usage limit and an
  availability time of 2026-08-31 11:52 local time. Recheck the live meter
  before starting R1.1.

## Five-hour execution contract

Each section targets 4 hours 15 minutes of execution and reserves 45 minutes
for sealing, replay, tests, documentation, and a clean handoff. Run at most
three isolated Luna/max evaluator tasks concurrently. Never batch adaptive
cases into one model context.

At 4:15, stop launching new provider tasks. Finish or isolate active attempts,
seal valid finals, replay all sealed keys, run the section checks, and update
`STATUS.md` and `FLAGS.md`. A section is not complete merely because five
hours elapsed. If a blocker remains, resume the same section in the next
window; do not advance to the next section.

Every section must self-heal infrastructure, schema, hash, staging, replay,
and deterministic-test failures before it is marked complete. Self-healing
must not edit a model final, weaken a verifier or threshold, discard a measured
failure, inspect hidden labels, or tune after hidden execution starts.

Use this prompt for each window:

> Execute only section R1.N from
> `docs/tasks/GOAL-R1-work-order.md`. Resume its durable checkpoint, use up to
> three isolated Luna/max workers, self-heal permitted failures, update project
> records, and stop at that section's terminal handoff. Do not start R1.N+1.

## R1.1 - dev replay from 22 to at least 60 rows

**Budget:** <= 5 hours.

1. Verify the 22-row replay checkpoint and exact pending roster.
2. Retry `drift_108519` from the unchanged frozen request with a fresh task
   identity; preserve its malformed prior final as diagnostic evidence.
3. Keep three one-case Luna/max workers saturated and process immutable pending
   run keys in frozen order.
4. Seal exact finals without editing, host-replay after small waves, and retain
   invalid/interrupted attempts under diagnostic identities.
5. Stop only after at least 60/102 rows are replayed, or after sealing every
   result obtainable before the 4:15 checkpoint rule.

**Handoff:** exact completed/pending run keys, metrics, failure maps, live
readiness JSON, and green replay/integrity tests.

## R1.2 - complete the 102-row dev trial

**Budget:** <= 5 hours. **Depends on:** R1.1.

1. Resume the frozen pending roster with three isolated workers.
2. Reach 102/102 terminal host-replayed rows.
3. Recompute all readiness gates: zero infrastructure failures, zero contract
   rejections, zero unverified emissions, answer rate >= 0.60, full-coverage F1
   >= 0.70, balanced accuracy >= 0.65, and answered accuracy >= 0.80.
4. Freeze the complete dev result as passing evidence or a non-headline failed
   trial. Do not make a release decision from a partial sample.

**Handoff:** a complete readiness artifact, immutable records and hashes, and
one explicit branch: `PASS_TO_FREEZE` or `REPAIR_REQUIRED`.

## R1.3 - bounded repair and qualification

**Budget:** <= 5 hours. **Depends on:** R1.2.

If R1.2 passes, audit reproducibility and skip method changes. If it fails:

1. Diagnose failures only from train/dev evidence.
2. Add regression tests before repair. Keep evidence guards, row isolation,
   bounded tools, anti-shortcut rules, and readiness thresholds unchanged.
3. Before any method-visible change, move the failed lineage under
   `data/eval/legacy/` with its explicit historical identity. Build a fresh
   numbered qualification lineage; never rewrite archived evidence or the
   existing canonical checkpoint.
4. Run a complete or statistically sufficient predeclared qualification within
   this window. If the repair cannot be fully qualified, checkpoint and resume
   R1.3 rather than advancing.
5. Require the same readiness thresholds and zero-failure gates as R1.2.

**Handoff:** one passing, reproducible method identity plus its exact runtime,
prompt, schema, verifier, source, and qualification hashes.

## R1.4 - predeclare configuration 4 and pass fresh smoke

**Budget:** <= 5 hours. **Depends on:** R1.3.

1. Freeze configuration 4 before any official call: method, prompt, schema,
   tool policy, verifier, budgets, seeds, source/runtime hashes, systems,
   thresholds, and unchanged hidden roster.
2. Prove one isolated exact-final qualification.
3. Run the fresh 14-row all-six-system smoke. Adaptive remains one case per
   task; provider-free controls may use their already-tested batching.
4. Seal and replay every result. Require 14/14 rows per system, zero
   infrastructure failures, zero counted repair substitutions, at least one
   verified non-null candidate from both agent systems, no unverified
   emissions, and a hash-bound global readiness artifact.

**Handoff:** immutable configuration freeze and green global smoke readiness.
If smoke fails, repair only within the permitted pre-hidden boundary and repeat
R1.4 under a new numbered freeze when required.

## R1.5 - begin the one-time hidden evaluation

**Budget:** <= 5 hours. **Depends on:** green R1.4.

**2026-09-23 recovery checkpoint:** Original GPT-5.6 Luna/max subagent logs
for `/root/r15_oracle_009`, `/root/r15_agent_020`, and
`/root/r15_adaptive_022` matched three saved finals byte-for-byte. Those
previously captured finals were sealed and replayed under the unchanged
official full-run identity. The checkpoint now has 78/305 sealed first-half
tasks and 227 pending; no new provider calls or hidden-case reruns occurred.
The local CLI reaches GPT-5.6 Luna/max but is a different transport, so fresh
official keys still require the frozen `collaboration_subagent` worker route.

**2026-09-23 user-directed GPT-6 Luna repeat:** The user authorized a fresh
`gpt-6-luna`/`max` evaluation. Preserve the original GPT-5.6 Luna run and its
78 sealed first-half tasks. Create a separate additive lineage with a new model,
request hashes, smoke qualification, all-system smoke, and full-run identity.
Run no new full task before its own smoke readiness gate. Since this repeats a
previously opened hidden roster, report its results as a follow-up comparison,
not as a first-look hidden-test estimate. Do not pool old and new model rows or
overwrite original artifacts.

1. Revalidate the freeze and prove the hidden roster is still unread.
2. Create one official hidden-run identity and immutable run-key order.
3. Execute the first deterministic half of pending run keys across all six
   systems with at most three workers. This is one run, not a pilot.
4. Checkpoint after every sealed key and replay in waves.
5. Once the run begins, do not tune, resample, change thresholds, replace
   measured failures, or restart for a better score.

**Handoff:** the same official run remains resumable, every attempted key is
terminal or explicitly interrupted, and no method state changed.

## R1.6 - finish hidden evaluation and temporal evaluation

**Budget:** <= 5 hours. **Depends on:** R1.5.

1. Resume only the remaining immutable official run keys.
2. Reach terminal all-six-system hidden coverage; preserve failures and
   unavailable telemetry as measured.
3. Run the frozen 20-pair / 40-side T6-v2 temporal evaluation required by T8.3.
4. Reconcile denominators, retries, resource telemetry, validity, quality, and
   fragile cells without pooling systems or rerunning for improvement.

**Handoff:** sealed full-run and temporal artifacts with complete replay and no
pending official keys.

### R1.6 terminal record (2026-10-06 IST)

Full coverage is 610/610 tasks and 196/196 canonical records per system;
all six host finalizations are VALID. Temporal coverage is 40/40 sides and
20/20 pairs, host validity VALID, paired accuracy 7/20 (35%) below the reporting
bar. The separate signed-reference audit preserves two full-run mismatches
(adaptive 154 and 173) and two entries in temporal side 40. No result was rerun
or revised after sealing. Resource telemetry remains not recorded. Per-system
metrics and drift-type cell denominators are reconciled without pooling.

See `data/eval/m4/gpt6-luna-repeat/diagnostics/r1.6-terminal-receipt.json`
and `diagnostics/r1.6-full-terminal-reconciliation.json` in that lineage.
Nineteen focused configuration tests and Ruff passed. This immutable R1.6
checkpoint preceded R1.7; its original receipt is preserved unchanged.

## R1.7 - T8.3/T8.4 reports and detector freeze

**Budget:** <= 5 hours. **Depends on:** R1.6.

1. Produce T8.3's validity/quality report covering historical configurations
   1-3, configuration 4, all six systems, T6-v2, retries, missing telemetry,
   fragile cells, and exact hashes.
2. Produce T8.4's performance profile and re-hash every narrative claim to
   machine-readable evidence.
3. Freeze exactly one detector decision: `GO`, `NO_GO`, or
   `NOT_EVALUABLE`.
4. Close or explicitly account for T7.2/T7.3; keep UI/T7.4 deferred.
5. Update `DATASHEET.md`, `STATUS.md`, `FLAGS.md`, and the GOAL-R2 input
   roster.
6. Verify that the completed evaluation remains canonical at the plain
   `data/eval/m4` path and that the exact frozen-path compatibility test for
   the 102 signed dev requests remains green.
7. Run focused tests, Ruff, artifact reconciliation, and a clean Git audit.

**Completion:** GOAL-R1 is complete only when reports, manifests, hashes, raw
evidence, resume state, and the detector decision reconcile and GOAL-R2 can
consume one frozen detector roster.

### R1.7 terminal record (2026-10-06 IST)

Canonical reports, performance profile, evidence/claim manifest, sole detector
decision, and migration input roster are under the plain `data/eval/m4` root.
The signed model cohort remains at its immutable `gpt6-luna-repeat` paths;
`evaluation-manifest.json` binds that storage without editing signed requests
or relabeling the paused original GPT-5.6 lineage. The decision is NOT_EVALUABLE
for four required signed-reference provenance mismatches, with host replay VALID
and failed descriptive balanced-accuracy, paired-significance, and temporal gates
preserved. Provider resource telemetry remains unavailable.

All 102 archived dev request/staging identities pass byte-integrity auditing;
the exact historical command mapping regression passes. The archived failed
trial is no longer an active command-path alias and is not represented as one.
The complete evaluation runtime is preserved as a hash-bound deterministic ZIP
before successor development. Thirty-four focused tests and Ruff pass. T7.2/T7.3
remain explicitly incomplete in release accounting; T7.4 remains deferred.

The R2 intake freezes zero active detector-led findings and 12 oracle-assisted
candidates requiring review/fixture promotion in R2.1. The user authorized a
persistent goal through every applicable R2 section and an additive AI-primary
migration review protocol with independent AI verification and adjudication.
These new reviews must remain explicitly non-human; no human attestations may
be manufactured, and candidate-only artifacts do not authorize generation.

## Naming and legacy rule

Completed artifacts and human-facing outputs use unversioned filesystem names.
An in-progress hash-bound execution tree may keep its frozen name only until
its terminal promotion step. Before replacement, move superseded evidence
under the nearest `legacy/` directory. Protocol and schema version values
embedded inside sealed records remain unchanged because they identify formats.

Current configuration tests likewise use plain `tests/test_config_*.py` names;
configuration-3 regression coverage lives under `tests/legacy/config3/`.
