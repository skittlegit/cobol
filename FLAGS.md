# FLAGS - active cross-track inbox

Last updated: **2026-09-23 IST**.

This file contains unresolved coordination items only. Resolved history belongs
in the applicable work order or immutable artifact.

## Release-wide

- **Model transition:** Use `gpt-6-sol` for new repository work. Preserve the
  original `gpt-5.6-luna`/`max` R1.5 run at 78/305 first-half tasks. The user
  authorized a separate `gpt-6-luna`/`max` follow-up with a new freeze at
  `data/eval/m4/gpt6-luna-repeat`; all 44 smoke tasks and its isolated
  qualification are sealed and replay valid, and all six smoke systems are
  `VALID`. The full-run identity and 610 requests are prepared with zero
  full-run provider calls. Execution is held for the user's estimate review.
  R2 migration generation will use `gpt-6-luna`/`max` after R2.2
  freezes fresh requests and passes qualification. Historical T6 reviews and
  evaluations retain their original model identities.
- **R1.2's archived trial is terminal at `REPAIR_REQUIRED`, and R1.3 has
  cleared the resulting repair work.** The complete 102/102
  configuration-4 dev trial has zero infrastructure failures, zero contract
  rejections, and zero unverified emissions. Answer rate 0.6765, F1 0.8571,
  and answered accuracy 0.8986 pass; balanced accuracy 0.4454 misses the 0.65
  gate. Preserve this as historical non-headline failed-trial evidence; it is
  not an active repair flag.
- **R1.3 qualification-2 failed and is archived; qualification-3 passed.** It completed 38/38 with
  clean infrastructure but missed all four metric gates (answer rate 0.5789,
  F1 0.4762, balanced accuracy 0.4896, answered accuracy 0.6364). D2, D3, D5,
  and D6 cross-class repair is complete locally. D2 passed 3/3; D3 was
  host-confirmed after arbitration repair; three distinct D5 boundary patterns
  classified correctly; and the final v7 D6/D7 probe passed 3/3 with every
  metric at 1.0 and no infrastructure, contract, or verification failures.
  Fresh official qualification-3 is terminal **VALID at 38/38**: answer rate
  0.9737, F1 0.9180, balanced accuracy 0.8542, and answered accuracy 0.8919.
  Infrastructure failures, contract rejections, unverified emissions, and
  pending rows are all zero. Invalid attempts remain diagnostics only.
- **R1.4 successor smoke passed globally.** The configuration-4 freeze at
  `data/eval/m4/global-smoke-lineage-3` completed 44/44 sealed tasks and 84/84
  host-replayed system-row evaluations. All six systems are `VALID` at 14/14,
  with zero infrastructure failures, repair substitutions, or unverified
  emissions. Global readiness artifact SHA-256 is
  `4506e7715f16588c6e211e63b86ab0753224502bd6dd650702d6907240dc3d0d`
  (canonical receipt identity
  `b4132bac53cd3ed4144927b20dbd5a2ce0d90ee3dcd36dafbecbc851bfc96de4`).
  The original R1.5 hidden evaluation is preserved and paused. Its full-run identity
  is `455d6f604b6f29b1fb7b14011bdfc2fbe7b28e18aea1205015774b72891e05b6`;
  78/305 R1.5 tasks are sealed and replay-valid and 227 remain. Three existing
  finals were matched byte-for-byte to their original GPT-5.6 Luna/max
  subagent sessions, then sealed and replayed with zero new provider calls.
  Schema-first
  capture validation and replay-driven resume selection protect sealed work.
  Preserve the remaining immutable pending keys; do not tune or restart for score.
- **Original R1.5 execution route:** the local Codex CLI can reach `gpt-5.6-luna`/`max`,
  but CLI execution is not the frozen `collaboration_subagent` transport. The
  current collaboration worker selector does not offer GPT-5.6 Luna. Run
  fresh original-lineage keys only when that exact worker route is available; do not seal
  CLI output as collaboration evidence.
- **Five-hour window guard.** R1.1-R1.7 and R2.1-R2.10 are separate runnable
  sections. Stop launching work at 4:15, reserve 45 minutes for a clean
  checkpoint, and resume the same section if it is not terminal. R1.3 closed
  as multi-window exceptions without restarting sealed rows. The GPT-6 Luna
  full run is prepared and held until the user starts it. The original R1.5
  checkpoint remains at `full/r1.5-checkpoint.json`.
- **UI remains deferred.** T7.4 is outside this release.
- **Remote T5.5/T5.5A is integrated.** The benchmark-first closure, ablation
  definitions, 71-row results, reports, code, and tests are retained. Their
  historical decision does not delete or supersede the user-authorized R1/R2
  successor path; R2.10 publishes the successor release addendum.
- **The Windows full-suite gate is green.** The current repair checkout passes
  761 tests with 71 skipped and 5 deselected. A transient `WinError 5` on the
  T6 atomic replacement path is repaired with bounded retry and covered by a
  regression test; the earlier `WinError 4551` parser-library block is not
  active on this host run.
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
- The successor-recovery method is now frozen and validated by R1.4's live
  all-six-system configuration-4 smoke.
- The bounded successor-development gate is 60 passed and Ruff clean; the
  root-cause receipt is under
  `data/eval/legacy/m4-config3/lineage-v4/diagnostics`. The fresh Luna/max
  train/dev qualification and configuration-4 predeclaration/smoke are now
  complete; the original R1.5 is preserved and the GPT-6 repeat is prepared.
- GOAL-R1 completed R1.2 at 102/102 with the historical
  `REPAIR_REQUIRED` branch, which R1.3 has resolved.
  R1.3 qualification-2 is archived failed, its repair is complete, and
  qualification-3 is VALID at 38/38. R1.4 is globally VALID; R1.5-R1.7 cover
  the single hidden run, temporal evaluation, and T8.3/T8.4.
- GOAL-R2 remains blocked until R1.7 and is split into R2.1-R2.10: ten
  conservative five-hour windows at the 24-task migration ceiling, or eight
  when only one 12-case track is eligible, for roster freeze, generation,
  validation, reporting, and release close.

## Clear conditions

- The successor adaptive-readiness flag is cleared by R1.4's valid all-six-
  system smoke. Configuration-3's `NOT_EVALUABLE` smoke remains immutable
  history.
