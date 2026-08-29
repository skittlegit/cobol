# FLAGS - active cross-track inbox

Last updated: **2026-08-29 14:05 IST**.

This file contains unresolved coordination items only. Resolved history belongs
in the applicable work order or immutable artifact.

## Release-wide

- **Live Luna execution is quota-blocked.** The provider reported availability
  at 2026-08-31 11:52 local time. The sandbox cannot independently read the
  meter. Resume only from the sealed 22/102 configuration-4 dev checkpoint.
- **Five-hour window guard.** R1.1-R1.7 and R2.1-R2.6 are separate runnable
  sections. Stop launching work at 4:15, reserve 45 minutes for a clean
  checkpoint, and resume the same section if it is not terminal.
- **UI remains deferred.** T7.4 is outside this release.
- **Remote T5.5/T5.5A is integrated.** The benchmark-first closure, ablation
  definitions, 71-row results, reports, code, and tests are retained. Their
  historical decision does not delete or supersede the user-authorized R1/R2
  successor path; R2.6 publishes the successor release addendum.
- **The Windows full-suite parser gate is host-policy blocked.** Application
  Control rejects the generated Tree-sitter COBOL DLL with `WinError 4551`.
  Focused migration, configuration, Phase-5, archived-path, and Ruff gates are
  green; rerun the full suite on a host that permits the local parser library.
- **Historical evidence is immutable.** Configuration 1's `NO_GO`,
  configuration 2's smoke stop, and configuration 3's rejected/stale lineages
  must not be overwritten.
- **Do not report an overall completion percentage.** Use exact durable task,
  evaluation, and gate counts.

## Track A - migration

- T6.2-T6.4 live migration is dependency-blocked, not implementation-blocked.
  T6.1 is complete and offline migration gates are green. Live patching waits
  for the configuration-4 detector freeze produced by R1.7.

## Track B - T6 review and promotion

- T6 promotion is cleared. Sol/max primary review, Luna/max independent review,
  adjudication, replacement ledgers, and promotion replay are sealed at exactly
  20 intact pairs / 40 sides. Invalid attempts remain diagnostics.

## Track C - configuration 3

- **Transport repair is locally complete.** Additive `lineage-v4` contains all
  37 self-contained requests for 84 evaluations, with zero provider calls at
  preparation time.
- **Focused gate:** 44 collaboration transport/staging/config-3 tests pass and
  the same files pass Ruff.
- Three v3 plain-LLM calls returned schema-valid outputs, then exposed a host
  replay bug around unavailable token telemetry. The outputs are preserved as
  diagnostics. V4 records usage as explicitly unavailable and reports resource
  summaries as `not_recorded`; it does not infer token counts.
- **Smoke execution is complete at 37/37 sealed tasks and 84/84 host-replayed
  evaluations.** `agent`, `plain_llm`, `rag_dense`, `rag_reranker`, and
  `oracle_slice` are VALID at 14/14 each. Invalid finals remain diagnostics.
- **Adaptive readiness is unresolved:** `adaptive_agent` completed 14/14 with
  zero pending keys but all rows abstained, so its terminal status is
  `NOT_EVALUABLE` and the global smoke-readiness artifact does not exist. This
  is a pre-hidden-test readiness failure, not a release `NO_GO`.
- Do not run the configuration-3 hidden test. The official smoke freeze cannot
  be tuned in place; method-affecting repair requires the additive numbered
  successor and fresh smoke defined by `docs/tasks/GOAL-R1-work-order.md`.
- The first successor-recovery tranche has classified every adaptive
  abstention and implemented the clause-grounded claim/class-arbitration prompt
  repair plus a fail-closed zero-success adaptive capture guard. These changes
  are not yet a frozen configuration or live result.
- The bounded successor-development gate is 60 passed and Ruff clean; the
  root-cause receipt is under
  `data/eval/legacy/m4-config3/lineage-v4/diagnostics`. A fresh Luna/max
  train/dev trial and configuration-4 predeclaration remain for GOAL-R1.
- GOAL-R1 is quota-paused. The configuration-4 Luna/max dev trial is at 22/102
  host-replayed cases with 80 pending and no active workers. R1.1 resumes the
  frozen roster; R1.2 completes dev; R1.3-R1.7 cover repair/qualification,
  smoke, the single hidden run, temporal evaluation, and T8.3/T8.4.
- GOAL-R2 remains blocked until R1.7 and is split into R2.1-R2.6 for roster
  freeze, generation, validation, reporting, and release close.

## Clear conditions

- Clear the quota flag only after a successful post-reset Luna task or a newer
  provider/user quota instruction.
- Clear the adaptive-readiness flag only after GOAL-R1 freezes a valid
  all-six-system successor smoke. Configuration-3's `NOT_EVALUABLE` smoke
  remains immutable history.
