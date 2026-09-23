# STATUS - current project dashboard

Last updated: **2026-09-23 IST**.

This is the authoritative current-state dashboard. Historical evidence remains
in `docs/tasks/` and immutable evaluation artifacts.

## Model transition

- New repository work uses `gpt-6-sol`. The original `gpt-5.6-luna`/`max`
  R1.5 lineage is preserved at 78/305 first-half tasks. Its sealed keys are
  not rerun or relabeled. The completed T6 reviews keep their recorded models.
- The user authorized a separate `gpt-6-luna`/`max` follow-up on 2026-09-23.
  Its additive freeze is under `data/eval/m4/gpt6-luna-repeat`; 44 official
  smoke tasks are sealed and replay valid, all six systems are `VALID`, and the
  all-system readiness receipt is verified. One isolated qualification is also
  sealed and replay valid. The frozen full-run preparation covers 196 rows and
  610 model tasks (305 in the first half), with zero full-run provider calls.
  Execution began at the user's request on 2026-09-23; only frozen pending
  keys may be scheduled. A repeated hidden-roster result must be described as a follow-up
  comparison, not a first-look estimate.
  The first handoff has **17/305** first-half keys sealed and replayed,
  **287** pending runnable keys, and **one** terminal contract rejection.
  See `full/r1.5-checkpoint.json` and `full/terminal-attempts.json` under the
  GPT-6 lineage. No second-half key has been launched.
- R2 migration generation is planned for `gpt-6-luna`/`max`. R2.2 must freeze
  new requests and pass a fresh qualification under that identity before live
  generation. R2 remains blocked on the R1.7 detector decision.

## Current outcome

- **T6.1 is complete.** The promoted T6-v2 benchmark is frozen at exactly 20
  pairs / 40 sides.
- **Configuration-3 transport repair is complete locally.** The corrected
  additive `lineage-v4` package contains all **37/37** self-contained smoke
  requests for **84 evaluations**. Preparation performed **zero provider calls**.
- **The repaired transport/staging gate is green:** **44 passed** across the
  collaboration transport, staging, preparation, controls, and live-runner
  tests; the same focused files pass Ruff.
- **Controlled `lineage-v4` smoke execution is complete:** **37/37 sealed
  tasks and 84/84 host-replayed evaluations**, with zero pending run keys.
  `agent`, `plain_llm`, `rag_dense`, `rag_reranker`, and `oracle_slice` are
  VALID at 14/14 each. Invalid model finals are preserved as diagnostics and
  never counted.
- **The adaptive smoke gate is `NOT_EVALUABLE`, not `NO_GO`.** All 14 adaptive
  rows reached a terminal host replay, but all 14 abstained; therefore the
  global all-six-system readiness artifact was not issued and no hidden-test
  evaluation is authorized. No test-set row has been executed.
- **Configuration-4 train/dev infrastructure is green.** The governed freeze,
  complete-dev materializer, replay/readiness scorer, and provider-free
  smoke/full runner pass a combined **95-test** gate with Ruff clean. All
  **102/102** dev rows now materialize; an earlier 94-row package is retained
  only as a superseded diagnostic.
- **R1.2's original trial is preserved as `REPAIR_REQUIRED`; R1.3 has now
  completed and cleared that repair requirement.** The controlled
  Luna/max configuration-4 dev trial at the canonical
  `data/eval/m4/lineage` tree
  contains exactly **102 requests / 102 staging trees**, with zero preparation
  provider calls and zero hidden-test rows. All **102/102** cases are sealed
  and host-replayed, none are pending, and there are zero
  infrastructure failures, zero contract rejections, and zero unverified
  emissions. Complete metrics are answer rate **0.6765**, full-coverage F1
  **0.8571**, balanced accuracy **0.4454**, and answered accuracy **0.8986**.
  Balanced accuracy missed the frozen **0.65** threshold; the terminal artifact
  is immutable non-headline failed-trial evidence and therefore still records
  its historical `REPAIR_REQUIRED` outcome; it is not the current project
  status. No hidden-test row was executed.
- **R1.3 bounded repair and qualification are complete.** Train/dev
  diagnosis found that conformance handling dominated the failed gate: only
  2/29 conformant rows emitted D7, 20/29 abstained, and 7/29 were false D5
  emissions. The failed R1.2 lineage is archived under
  `data/eval/legacy/m4-config4/lineage-1-r1_2-failed`; the method-visible D7/D5
  repair and regression coverage are implemented. Fresh `qualification-2`
  completed **38/38** with clean infrastructure but is archived as failed at
  `data/eval/legacy/m4-config4/lineage-2-r1_3-qualification-failed`:
  answer rate 0.5789, F1 0.4762, balanced accuracy 0.4896, and answered
  accuracy 0.6364. Cross-class repair is now locally cleared: D2 passed 3/3,
  D3 arbitration passed host replay, all three D5 boundary semantics classified
  correctly, and the final v7 D6/D7 probe passed 3/3 with answer rate, F1,
  balanced accuracy, and answered accuracy all 1.0. Official fresh
  `qualification-3` completed **38/38 sealed rows** and terminal host replay is
  **VALID**: answer rate **0.9737**, full-coverage F1 **0.9180**, balanced
  accuracy **0.8542**, and answered accuracy **0.8919**. Infrastructure
  failures, contract rejections, unverified emissions, and pending rows are
  all zero. Invalid attempts remain quarantined diagnostics. No hidden-test
  row has been executed. The readiness artifact SHA-256 is
  `1a13024d7a4f7e6dbd179279c5cf588edcbca7e68b20a7158b83e0ddd7dc6c22`.
- **R1.4 configuration-4 smoke is complete and globally `VALID`.** The
  immutable freeze is under `data/eval/m4/global-smoke-lineage-3`, freeze
  SHA-256 `25a538298d6ff9ec76afcb5e0f91f5771cfa37db8d567bf1392a8ba40083fd52`.
  All **44/44** official task bundles are sealed and all six systems replay
  **14/14** rows each (**84/84** system-row evaluations): `agent`,
  `adaptive_agent`, `plain_llm`, `rag_dense`, `rag_reranker`, and
  `oracle_slice` are `VALID`. There are zero infrastructure failures, zero
  counted repair substitutions, and zero unverified emissions; the two agent
  systems produced 11 and 10 verified non-null candidates. The hash-bound
  global readiness artifact SHA-256 is
  `4506e7715f16588c6e211e63b86ab0753224502bd6dd650702d6907240dc3d0d`
  (canonical receipt identity
  `b4132bac53cd3ed4144927b20dbd5a2ce0d90ee3dcd36dafbecbc851bfc96de4`).
  Invalid and quota-interrupted attempts remain diagnostics only.
- **The original R1.5 hidden run is preserved and paused.** Its full-run
  identity is `455d6f604b6f29b1fb7b14011bdfc2fbe7b28e18aea1205015774b72891e05b6`:
  196 frozen test rows, 610 all-six-system tasks in the complete run, and 305
  deterministic first-half tasks assigned to R1.5. Exactly **78/305** are
  sealed and replay-valid; **227 remain in that lineage**. Three previously captured finals
  were recovered from matching original GPT-5.6 Luna/max subagent session logs
  and sealed without new provider calls. The exact resumable evidence is
  `full/r1.5-checkpoint.json`; schema validation and replay-driven resume
  selection prevent sealed keys from being scheduled again. No tuning, resampling,
  threshold change, or score-driven restart has occurred. The separate GPT-6
  Luna repeat has passed smoke, and its full run began on 2026-09-23 under the
  frozen identity. Record sealed progress in its own checkpoint.
- **R1 and R2 are divided into five-hour windows.** R1 has seven sequential
  sections. R2 now has ten conservative sections at the 24-task migration
  ceiling (50 planned hours), or eight sections when only one 12-case track is
  eligible (40 planned hours); each reserves the final 45 minutes for a clean
  replay/documentation handoff and must resume the same section if incomplete.
  R1.3 and R1.4 completed as multi-window exceptions without restarting sealed
  rows. The GPT-6 repeat is now executing from its immutable task order.
- **Artifact naming and cleanup are reconciled.** The earlier configuration-4
  dev checkpoint used `data/eval/m4/lineage` and plain operational filenames.
  Its frozen-path compatibility replay preserved exactly 22 completed / 80 pending rows, the
  same freeze hash and metrics, and zero infrastructure/contract failures.
  The pre-freeze benchmark is under `data/benchmark/legacy/v1-pre`; unused
  config-4 lineage-1 and the old 179 MB M4-v3 worker/cache tree were removed.
  Active `benchmark/v1` and `t6-v2` remain because sealed R1/R2 identities
  still require them.
- **Test and T5.5 naming migrations are validated.** Current configuration-4
  tests use plain `test_config_*` names; configuration-3 regression tests live
  under `tests/legacy/config3`. The remaining `phase5` and `t6_v2` test names
  identify tasks/protocols rather than competing file revisions. Remote T5.5
  and T5.5A are merged: the benchmark-first closure and five 71-row core
  ablations are preserved under `data/eval/m5`. T5.5 closes the historical
  configuration-1/T5.4 analysis; R2.10 still owes the successor detector,
  migration, and release addendum without rewriting that evidence.
- **Focused post-migration verification is green:** 65 configuration/transport
  tests, 34 Phase-5/ablation tests, 95 runtime/schema/policy-hunt tests, and
  105 T6 tests all pass, with repository-wide Ruff clean. The current checkout's
  full pytest gate is green at **761 passed, 71 skipped, and 5 deselected**.
  The Windows atomic-write path now retries transient destination locks with a
  bounded backoff, and its new regression plus the formerly failing 22-item
  runner test pass. Pytest uses the ignored repository-local `.pytest_tmp`
  root required by fail-closed evidence-path tests, and legacy CRLF T6 pins
  validate consistently on LF GitHub checkouts without accepting content
  changes. A separate index export using Git's exact LF blobs passes at **642
  passed, 183 platform-skipped, and 5 deselected**.
- **UI/T7.4 remains deferred.**

## Live release path

| Gate | State | Evidence | Remaining work |
|---|---|---|---|
| Successor configuration-4 smoke | R1.4 globally VALID | 44/44 sealed tasks; 84/84 system-row evaluations; all six systems VALID; readiness artifact SHA-256 `4506e7715f16588c6e211e63b86ab0753224502bd6dd650702d6907240dc3d0d` | None |
| Sol/max AI-primary T6 review | sealed | 22 accepted responses; invalid first attempts retained | None |
| Luna/max independent T6 review | sealed | 22/22 accepted | None |
| T6 comparison and adjudication | sealed | 12 disputes adjudicated; replacement ledgers replayed | None |
| T6 promotion | done | Final manifest validates 20 pairs / 40 sides | None |
| Config-3 transport repair | ready | Additive `lineage-v4`; 37/37 requests; 44 focused tests pass | No implementation blocker remains before smoke |
| Config-3 smoke | terminal `NOT_EVALUABLE` for the candidate | 37/37 sealed tasks; 84/84 host-replayed evaluations; five systems VALID; adaptive 14/14 abstained | Preserve as configuration-3 evidence; repair only through the governed successor path |
| Original detector/full evaluation | Preserved and paused | Immutable identity `455d6f604b6f29b1fb7b14011bdfc2fbe7b28e18aea1205015774b72891e05b6`; 78/305 R1.5 tasks sealed and replay-valid | Preserve 227 pending keys and the original model identity |
| GPT-6 Luna follow-up evaluation | Smoke VALID; full run in progress | 44/44 smoke tasks sealed; six systems VALID; 196 hidden rows, 610 frozen full-run requests; 17/305 first-half keys sealed, 1 terminal contract rejection | Resume 287 pending runnable first-half keys; preserve original R1.5 separately |
| T6.2-T6.4 migration | ready offline, live pending | Offline migration suite previously 30/30 green | Run after detector freeze |
| M5/release record | historical T5.5/T5.5A closed; successor addendum pending | `benchmark-first-analysis` and `ablations/report`; historical T5.4 remains immutable | Integrate configuration-4 and migration results in R2.6 |

## Next execution order

1. Continue the GPT-6 Luna follow-up full run
   from `data/eval/m4/gpt6-luna-repeat`. Preserve the original R1.5 keys and
   follow the five-hour handoff rule in `docs/tasks/GOAL-R1-work-order.md`.
   Continue R1.6 and R1.7 only after the full-run handoff is terminal.
2. After R1.7 freezes the detector roster, run R2.1 through R2.10 sequentially
   from `docs/tasks/GOAL-R2-work-order.md` under the same window rule.
3. Keep UI/T7.4 deferred.

## Configuration-3 evidence pins

- Repaired canonical freeze:
  `data/eval/legacy/m4-config3/lineage-v4/run-freeze-v2.json`
  - artifact SHA-256:
    `18cf584cf5adebbafa35ba52bf4cf1ddfa718f38186a8db5af2080142bd1aead`
  - canonical freeze SHA-256:
    `7c20cf2a49dccc731b5630a6a76b6fe7ef06ccd166a3ca25b137064398a95aea`
- Repaired smoke plan:
  `data/eval/legacy/m4-config3/collaboration-smoke-plan-v2.json`
  - SHA-256:
    `74058d19a84fb9706d5f488a14cc4681e9737d3fbf9badbb6726700dbc9e5948`
- Preparation receipt:
  `data/eval/legacy/m4-config3/lineage-v4/smoke-request-preparation-v2.json`
  - SHA-256:
    `251f8155f2c8c8a03142afb8e32803fee8a4cb6aba38f78ddaec1a52dee39e07`
  - 14 benchmark rows, 37 tasks, 84 planned evaluations, zero provider calls
  - request counts: agent 7, adaptive agent 14, plain LLM 3, dense RAG 3,
    reranker RAG 3, oracle slice 7
- The receipt's literal status is
  `MODEL_PROMPTS_READY_TRANSCRIPT_PROTOCOL_PENDING`; it is a prompt-preparation
  receipt, not the transport readiness verdict. Capture/staging readiness is
  established separately by the 43-test gate. The frozen receipt is not
  rewritten after the fact.
- Earlier v1, partial/stale v2, and three sealed v3 plain-LLM outputs remain
  preserved diagnostics. They are not valid v4 smoke results.
- Final system progress is stored under
  `data/eval/legacy/m4-config3/lineage-v4/smoke/*/progress.json`. Five systems are
  `VALID`; `adaptive_agent/progress.json` is `NOT_EVALUABLE` with 14 completed
  keys, zero pending IDs, and zero interruptions.

## Other evidence pins

- Final T6-v2 manifest:
  `data/benchmark/t6-v2/final/manifest.json` - SHA-256
  `290d69d1732011895bb0d198c8d0a1dd23536f00c635e6f2da5a868f4e2838f`.
- AI-primary audit:
  `data/benchmark/t6-v2/review/ai-primary-collaboration/audit-manifest.json` -
  SHA-256
  `5a5fd809b7126f36e5523abba3ebef351978381afe943598503bd3c9385484d4`.
- Independent Luna audit:
  `data/benchmark/t6-v2/review/evidence/luna-independent-collaboration-subagent/audit-manifest.json`
  - SHA-256
  `c9cd7338402ba5c1b9ad621bdcca1be52e5222293bd22d82f3050008a998d2d1`.
- Final primary-vs-Luna comparison:
  `data/benchmark/t6-v2/review/evidence/comparison/primary-vs-luna.final.json`
  - SHA-256
  `da6cffee8f067f30b0f13aa3a75ea0e5d5681173b2ebbe958d87e1fcd36543b2`.
- Adaptive smoke root-cause record:
  `data/eval/legacy/m4-config3/lineage-v4/diagnostics/adaptive-smoke-root-cause-v1.json`.
  It reconciles all 14 abstentions, records the unchanged integrity gates,
  reports 60 focused tests passing plus Ruff, and confirms zero hidden-test
  rows and zero successor provider calls.

## Constraints and decisions

- AI-primary and adjudicator evidence is explicitly non-human. No artifact may
  represent model review as human review.
- The controlled evaluation path is `collaboration_subagent` with
  `gpt-5.6-luna` at `max` reasoning.
- Native ChatGPT OAuth and WSL are optional legacy transports, not release
  requirements.
- Promotion, smoke readiness, full-run readiness, migration, and release
  reporting fail closed when required hashes or replay evidence are missing.
- Configuration 1's valid `NO_GO` and configuration 2's smoke stop remain
  immutable historical evidence.
- Do not report a synthetic overall completion percentage. Report exact task,
  evaluation, and gate counts.

## Compact task ledger

| Tasks | State |
|---|---|
| T0.1-T5.4 | done; historical milestone artifacts retained |
| T5.5 | done for frozen T5.4 benchmark-first analysis; successor release addendum remains in R2.6 |
| T5.5A | done; five core ablations frozen at 71/71 rows each |
| T6.1 | done; final T6-v2 is 20 pairs / 40 sides |
| T6.2 | blocked on config-3 detector freeze |
| T6.3 | blocked on T6.2 |
| T6.4 | blocked on T6.3 |
| T7.1 | done |
| T7.2-T7.3 | pending |
| T7.4 | deferred |
| T7.5 | pending M5 |
| T8.1 | done for additive `lineage-v4` transport/request preparation |
| T8.2 | done offline |
| T8.3 | configuration-4 successor smoke globally VALID at 44/44 tasks and 84/84 system-row evaluations; immutable R1.5 hidden run active at 78/305 sealed tasks |
| T8.4 | queued in GOAL-R1 after a valid successor smoke/full run |
| GOAL-R1 | R1.4 globally VALID; R1.5-R1.7 remain |
| GOAL-R2 | blocked on R1.7; ten conservative five-hour sections R2.1-R2.10 at the 24-task ceiling (eight if only one 12-case track is eligible) cover T6.2-T6.4 and the successor release addendum/close |

## Update policy

Update this file whenever a live gate changes, a persisted count changes, an
evidence hash is frozen, the quota guard changes state, or a release decision is
made. Never advance live counts until host replay validates the artifacts.
