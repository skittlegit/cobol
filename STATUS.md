# STATUS - current project dashboard

Last updated: **2026-08-25 18:03 IST**.

This is the authoritative current-state dashboard. Historical evidence remains
in `docs/tasks/` and immutable evaluation artifacts.

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
- **The controlled Luna/max configuration-4 dev trial is live.** `lineage-v2`
  contains exactly **102 requests / 102 staging trees**, with zero preparation
  provider calls and zero hidden-test rows. At this checkpoint **13/102** cases
  are sealed and host-replayed, **89** are pending, and there are zero
  infrastructure failures, zero contract rejections, and zero unverified
  emissions. Partial metrics are answer rate **0.6154**, full-coverage F1
  **0.800**, balanced accuracy **0.475**, and answered accuracy **0.875**.
  Three isolated `gpt-5.6-luna` / `max` workers are kept active concurrently.
- **The latest user-observed quota reading was 20% remaining.** The sandbox
  cannot read the current meter, so no exact live balance is claimed.
- **UI/T7.4 remains deferred.**

## Live release path

| Gate | State | Evidence | Remaining work |
|---|---|---|---|
| Successor adaptive recovery | live configuration-4 dev trial; 13/102 replayed | `m4-config4/lineage-v2`; 102/102 materializable; 95-test provider-free gate; partial F1 0.800 | Complete the remaining 89 dev cases and freeze only if every readiness gate passes |
| Sol/max AI-primary T6 review | sealed | 22 accepted responses; invalid first attempts retained | None |
| Luna/max independent T6 review | sealed | 22/22 accepted | None |
| T6 comparison and adjudication | sealed | 12 disputes adjudicated; replacement ledgers replayed | None |
| T6 promotion | done | Final manifest validates 20 pairs / 40 sides | None |
| Config-3 transport repair | ready | Additive `lineage-v4`; 37/37 requests; 44 focused tests pass | No implementation blocker remains before smoke |
| Config-3 smoke | terminal `NOT_EVALUABLE` for the candidate | 37/37 sealed tasks; 84/84 host-replayed evaluations; five systems VALID; adaptive 14/14 abstained | Preserve as configuration-3 evidence; repair only through the governed successor path |
| Successor detector/full evaluation | active on train/dev | `docs/tasks/GOAL-R1-work-order.md`; hidden test remains unexecuted | Finish config-4 dev readiness, predeclare, pass fresh all-six smoke, then run the hidden test once |
| T6.2-T6.4 migration | ready offline, live pending | Offline migration suite previously 30/30 green | Run after detector freeze |
| M5/release record | pending | Historical T5.4 remains immutable | Integrate config-3 and migration results |

## Next execution order

1. Continue GOAL-R1 in this prompt without creating another `/goal`: finish the
   102-row dev trial, repair/retry without weakening evidence gates,
   predeclare the numbered successor, pass a fresh smoke, run the still-unread
   hidden test once, and freeze T8.3/T8.4.
2. Start a later separate `/goal` with
   `docs/tasks/GOAL-R2-work-order.md`. It executes T6.2-T6.4, validates the
   non-pooled detector/oracle migration tracks, and freezes T5.5/M5 and the
   release record.
3. Re-read the signed-in weekly quota meter before each order. The approximate
   40-point size is a planning estimate, not a stop condition: an order must
   finish active repairs, retries, replay, and validation before handoff.
4. Keep UI/T7.4 deferred.

## Configuration-3 evidence pins

- Repaired canonical freeze:
  `data/eval/m4-config3/lineage-v4/run-freeze-v2.json`
  - artifact SHA-256:
    `18cf584cf5adebbafa35ba52bf4cf1ddfa718f38186a8db5af2080142bd1aead`
  - canonical freeze SHA-256:
    `7c20cf2a49dccc731b5630a6a76b6fe7ef06ccd166a3ca25b137064398a95aea`
- Repaired smoke plan:
  `data/eval/m4-config3/collaboration-smoke-plan-v2.json`
  - SHA-256:
    `74058d19a84fb9706d5f488a14cc4681e9737d3fbf9badbb6726700dbc9e5948`
- Preparation receipt:
  `data/eval/m4-config3/lineage-v4/smoke-request-preparation-v2.json`
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
  `data/eval/m4-config3/lineage-v4/smoke/*/progress.json`. Five systems are
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
  `data/eval/m4-config3/lineage-v4/diagnostics/adaptive-smoke-root-cause-v1.json`.
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
| T5.5 | pending configuration 3 and T6.4 |
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
| T8.3 | configuration-3 smoke complete at 37/37 tasks and 84/84 evaluations; adaptive gate `NOT_EVALUABLE`; full run not authorized |
| T8.4 | queued in GOAL-R1 after a valid successor smoke/full run |
| GOAL-R1 | active in this prompt; config-4 dev trial 13/102 replayed with three Luna/max workers; smoke/full/T6/T8.3-T8.4 remain |
| GOAL-R2 | ~40 points; ready after GOAL-R1 for T6.2-T6.4, T5.5/M5, and release close |

## Update policy

Update this file whenever a live gate changes, a persisted count changes, an
evidence hash is frozen, the quota guard changes state, or a release decision is
made. Never advance live counts until host replay validates the artifacts.
