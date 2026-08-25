# GOAL-R1 work order - adaptive recovery and detector freeze

**Owner:** Track C  
**State:** first recovery tranche complete; ready for the remaining `/goal` run  
**Projected remaining usage:** approximately 40 weekly-quota percentage points  
**Depends on:** immutable configuration-3 `lineage-v4` smoke evidence and T6.1  
**Canonical outputs:** a new numbered candidate freeze, its sealed smoke/full
artifacts, the T8.3 report, and the T8.4 performance profile

## Outcome

Recover the proper adaptive detector on train/dev without weakening evidence
or verification, freeze the repaired method as a new numbered configuration,
pass a fresh all-six-system smoke, run the still-unread hidden test exactly
once, and freeze the detector and performance decisions consumed by migration.

Configuration 3 is historical evidence, not a result to rewrite. Its official
smoke completed all 37 tasks / 84 evaluations, but the adaptive system ended
`NOT_EVALUABLE`: 14/14 rows abstained and the global smoke-readiness artifact
could not be issued. The other five systems are `VALID` at 14/14 each. No
hidden-test row has been executed, so the existing hidden test remains
untouched.

## Why this is a successor configuration

T8.2 froze the configuration-3 method before the official smoke and requires a
new numbered configuration after any method, prompt, budget, verifier,
threshold, or sample change. Therefore:

- preserve `data/eval/m4-config3/lineage-v4/` byte-for-byte;
- use an additive transport-only lineage only for a proven transport repair
  that leaves model-visible and verifier behavior identical;
- otherwise predeclare configuration 4, including method identity, prompt,
  schema, tool policy, verifier identity, budgets, seeds, source/runtime
  hashes, systems, gates, and the unchanged hidden-test roster; and
- never relabel configuration-3 outputs as configuration 4.

## Completed approximately 20-point recovery tranche

The 2026-08-25 continuation used the user-authorized tranche to classify all
14 adaptive abstentions and implement the first bounded repairs:

- clarified that `claim` must be a clause-grounded regulatory proposition and
  that implementation facts belong in prediction rationale;
- added D1/D3 and D2/D7 arbitration, complete canonical D4-member guidance,
  exact ledger-hash preflight, and command-invocation retry guidance;
- preserved the lexical verifier threshold and every evidence guard;
- made adaptive collaboration sealing fail closed when a capture has zero
  successful staged observations, while preserving baseline no-tool captures
  and evidence-based explicit abstentions; and
- added focused prompt, lexical-claim, and transport regression tests.

The root-cause record is
`data/eval/m4-config3/lineage-v4/diagnostics/adaptive-smoke-root-cause-v1.json`.
The combined focused successor-development gate is 60 passed and Ruff clean.

This is un-frozen train/dev engineering for configuration 4. No successor
provider trial, official smoke, hidden-test call, or migration call occurred.

## Estimated remaining 40-point allocation

| Phase | Planning points | Required result |
|---|---:|---|
| Finish train/dev adaptive trials | 8 | Readiness thresholds pass without verifier relaxation |
| Configuration-4 freeze and transport qualification | 8 | Immutable identities and clean exact-final capture |
| Fresh all-six smoke | 8 | Global smoke readiness is hash-bound and green |
| One-time full evaluation | 12 | Detector and temporal decisions are frozen |
| T8.4 performance profile and handoff | 4 | Claims re-hash to sealed events |

The allocation is an estimate, not a termination rule.

## Execution

1. Reconcile the configuration-3 terminal artifacts before further changes.
   Confirm 37/37 sealed tasks, 84/84 replayed evaluations, five `VALID`
   systems, adaptive `NOT_EVALUABLE`, zero pending run keys, and preservation
   of every invalid attempt under diagnostics.
2. Retain the completed root-cause reproductions on unit fixtures and
   train/dev only:
   missing successful staging observations, lexical citation rejections,
   incomplete D2 negative-evidence paths, D4 enum rationale rejection, and
   ledger observation-hash mismatch. Determine whether each is transport,
   orchestration, method, or verifier behavior. Do not inspect hidden-test
   rows, labels, scores, or T6-v2 evaluation answers.
3. Extend the regression tests before each additional fix. Repair staging identity/logging and
   exact-final capture as infrastructure. For method-affecting changes, create
   the numbered successor predeclaration; do not relax verification,
   evidence thresholds, bounded tools, row isolation, or anti-shortcut rules.
4. Iterate Luna/max engineering trials only on train/dev until a complete
   trial has zero infrastructure/contract failures, zero unverified emissions,
   answer rate at least 0.60, full-coverage F1 at least 0.70, balanced accuracy
   at least 0.65, and answered accuracy at least 0.80. Retain failed trials as
   non-headline diagnostics.
5. Freeze all identities before the next official call. Prove exact request,
   source, tool-log, event, final, schema, and replay binding in an isolated
   qualification. Record provider usage/timing as `not_recorded` where the
   in-product transport does not expose it; never infer or zero-fill it.
6. Run the fresh 14-row, all-six-system smoke with ChatGPT-authenticated
   `gpt-5.6-luna`, `max`, one case per adaptive task, and at most three
   independent tasks concurrently. Seal/replay every accepted result. The
   gate requires 14/14 exact rows per system, zero infrastructure failures,
   zero counted contract-rejection repairs, at least one non-null verified
   candidate from both agent systems, no unverified emissions, and a frozen
   global readiness artifact.
7. Only after that gate is green, run the frozen hidden test once. Resume only
   immutable run keys after infrastructure or quota interruptions. Once the
   hidden run begins, do not tune, resample, change thresholds, replace
   failures, or rerun for a better score.
8. Produce T8.3's full validity/quality report and T8.4's performance profile.
   Include the 20-pair / 40-side T6-v2 temporal evaluation, historical
   configurations 1-3, missing telemetry, fragile cells, retries, and exact
   artifact hashes. Freeze one `GO`, `NO_GO`, or `NOT_EVALUABLE` detector
   decision from the measured evidence.

## Self-healing and stop rules

- Checkpoint after every sealed run key; resume instead of restarting.
- A malformed or interrupted model attempt is isolated under a new diagnostic
  identity and retried fresh before the official result is counted.
- A failed test, hash, staging, replay, or report gate must be diagnosed,
  repaired within the permitted development boundary, rerun, and validated.
- If a repair would change a frozen method, create the required successor
  configuration rather than mutating the freeze.
- The projected 50 points do not stop an in-progress repair, retry, replay, or
  validation. Stop only at a clean terminal checkpoint with no broken staging
  state and a frozen detector decision.
- Self-healing never means tuning against the hidden test, weakening a gate,
  discarding a measured failure, or converting missing evidence into a pass.

## Completion handoff

This order is complete when the detector decision, full report, performance
profile, manifests, hashes, raw evidence, and resume state reconcile; T7.2 and
T7.3 are closed or explicitly accounted for; `STATUS.md`, `FLAGS.md`, and
`DATASHEET.md` name the new evidence; and GOAL-R2 can consume a single frozen
detector roster. UI/T7.4 remains excluded.
