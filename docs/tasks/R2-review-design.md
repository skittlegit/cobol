# R2 AI migration review implementation design

This is a design aid for the canonical GOAL-R2 and T6 work orders. It does not
freeze a roster, authorize a provider submission by itself, or supersede a work
order. The user explicitly authorized AI-primary migration review with
independent AI verification and adjudication. All new review evidence must be
explicitly nonhuman. Implementation and execution wait for the R1.7 terminal
handoff; historical human-only contracts and completed evaluation remain intact.

## Policy and model identities

Use fresh one-case contexts for primary, independent verifier, and adjudicator.
Independence means separate contexts and captured task identities; it does not
establish independence of model errors. Primary and verifier never receive each
other's response. Adjudication receives both only after they are sealed.

`CLAUDE.md` selects `gpt-6.1-sol` for new implementation and review work. Freeze
that review identity prospectively, including its actual reasoning setting and
transport. R2 generation remains separately `gpt-6-luna`/`max`. Do not infer that
the generation model decision authorizes silently changing review models. A
different-model verifier may be selected prospectively only through an explicit
work-order/model decision. Completed Sol/Luna temporal reviews are historical
precedent for the workflow, not migration-case responses.

## Additive contracts

Create `migration/ai_review.py` or equivalent additive module. Keep existing
`MigrationReviewProtocol`, `MigrationReviewResponse`, `ExternalReviewerVerification`,
`CanonicalReviewEvidence`, and `load_canonical_roster` unchanged. Never set
`human_reviewer_verified=true` for an AI reviewer or reinterpret the historical
`human_primary_reviewed_and_verified` literal.

New strict, frozen models should include:

| Model/schema | Required bindings |
|---|---|
| `migration-ai-review-protocol-v1` | Frozen timestamp; authorization/policy pin; candidate-manifest hash; exact ordered 12 candidate IDs; role identities/model/reasoning/transport; prompt and response-schema hashes; coordinator/runtime hashes; predeclared duplicate-source policy; review budgets; nonhuman provenance |
| `migration-ai-review-case-input-v1` | Opaque case alias; materialized source paths and exact bytes/hashes; applicable regulation text/version/date/hash; proposed allowed source spans; intended and unaffected fixture specifications; capabilities/affected hosts; source-bundle group; fixture/runtime pins |
| `migration-ai-review-request-v1` | Case alias, role, immutable protocol/input hashes, exact prompt/schema hashes, requested model/reasoning, task key derived from these fields |
| `migration-ai-review-response-v1` | Alias, role, `include`/`exclude`/`needs_revision`, grounded rationale, allowed-scope findings, intended/regression fixture judgments, capability judgment, duplicate-source judgment, unresolved issues; no provider-owned identity or usage fields |
| `migration-ai-review-capture-v1` | Host-bound request/task identity, exact final artifact/hash, captured events/transcript hashes, actual available model identity evidence, authoritative timestamps where available, isolation limitations, unavailable telemetry as `not_recorded` |
| `migration-ai-review-evidence-v1` | Protocol/input pins; primary/verifier/adjudicator request and capture pins; reconciled inclusion decision; explicit `review_provenance=ai_primary_independent_ai_verification_and_adjudication`; three distinct task/context identities; nonhuman flag |
| `migration-ai-reviewed-case-v1` | Existing source/scope/behavior/capability fields, validation protocol hash, AI review evidence hash, `review_state=ai_primary_reviewed_verified_and_adjudicated`, `eligible_for_evaluation=true` only after all promotion gates |

A host signature can bind captured bytes to a host receipt. It cannot prove a
human identity or invent a provider capability. Any signing key registry must
be frozen before use and labeled host-attestation, with no private key included
in released artifacts. Existing raw capture machinery may supply stronger
request/final/transcript bindings than a new signature; preserve those bindings.

## Case preparation and concrete fixtures

Start from the preselected candidate manifest: 12 cases, two per D1-D6, six
local/six interprocedural, eight batch/four copybook fan-out, zero CICS, nine
distinct materialized bundles. Do not choose replacements using detector scores.
Preserve candidate files unchanged. Stage exact materialized sources and verify
their original pins before designing fixtures.

Create case-local fixtures with explicit inputs, observable outputs, intended
post-remediation expectations, and unaffected expectations. Descriptions alone
are not executable tests. Keep hidden benchmark labels, mutation provenance,
Git history, unrelated cases, detector scores, and any generated remediation
patch out of review packets. A source-grounded proposed regulatory assertion
and scope may be reviewed, but raw benchmark gold is not an independent label.
Reviewers must identify underspecified or unsupported assertions.

Allowlisted source spans must cover the smallest justified repair scope, frozen
before generation. If a proposed scope or fixture is rejected, retain the first
review and prepare a new numbered input identity; repeat the complete affected
review chain before promotion. Never rewrite signed inputs or force inclusion.

Resolve or explicitly justify these dependent-source pairs:

- `migration_075075` / `migration_255807`;
- `migration_106241` / `migration_548537`;
- `migration_052199` / `migration_071627`.

If retained, report both 12 cases and nine source bundles, preserve group IDs,
and use bundle-level uncertainty or disclose that case-level intervals ignore
dependence. If excluded, publish the changed denominator and wave schedule.

## Prompt and execution plan

Primary system instruction: review one proposed COBOL migration case using
only its supplied source, regulation, scope, and fixture packet. Do not propose
a patch. Decide whether the intended change is justified, whether unaffected
checks constrain regressions, whether allowed scope is sufficient and bounded,
and whether claimed validation capability is real. Return only the exact typed
review response; exclude or request revision when evidence is insufficient.

Verifier receives the same immutable source/fixture packet with a distinct
instruction to independently challenge scope, boundary semantics, call/copybook
effects, fixtures, and capability. It receives no primary rationale or decision.

Adjudicator receives the same packet plus exact sealed primary/verifier finals.
Resolve every disagreement explicitly and explain inclusion/exclusion. Require
adjudication for every case, including agreements, to preserve the existing
three-role promotion standard. Do not repair a reviewer final manually.

The initial review denominator is 36 one-case submissions, plus immutable
replacement-input reviews when needed. These are preparation/review tasks,
separate from the at-most-24 migration generation denominator. Publish their
additional time/usage rather than hiding them in generation counts. Use no
cross-case worker reuse. Run a non-live fixture qualification first, then seal
each exact final, validate schema and capture identities, and preserve malformed
or interrupted attempts. Resume unchanged requests only where no terminal
capture exists. Provider limits cannot be resolved by fabricated host results.

## Promotion and successor compatibility

Implement `load_ai_canonical_roster` as a separate fail-closed entry point.
Validate all input/request/capture/evidence hashes and schema identities,
distinct role/context identities, temporal ordering, case order/uniqueness,
actual approved decisions, frozen scope/fixture bindings, and nonhuman flags.
Promotion writes canonical `data/migration/cases.jsonl` with an unversioned
manifest selecting the additive schema. Retain all candidate/rejected evidence.

An additive R2 request/validator/report path must accept the reviewed AI case
without casting it into the human-only case model. Reuse parser, patch apply,
scope, and validation routines through a narrow shared case protocol where
necessary; keep the old human loader and report tests valid. Freeze the final
runtime after these changes and before generation. Old R1 sealed runtime
snapshots and hashes remain historical and must not be regenerated.

Bind R2 activation to R1.7's exact successor detector decision and receipt,
rather than pretending it is configuration 3. Non-GO gives zero detector-led
tasks; reviewed oracle-assisted cases remain separately eligible. Every oracle
request contains only its authorized finding/source/scope; detector/oracle
evidence never pools. Freeze exact per-track counts, run-key order, and waves.

## Real validation backend

Implement a pinned case-local backend rather than test `PassingBackend` stubs.
Parser checks must use the existing line-preserving preprocessing and vendored
grammar. Static checks must inspect actual call graph/dataflow/slice/reference
integrity and every affected copybook host. Fixture behavior must execute real
case-specific tests when supported, with bounded timeouts and retained logs.

Probe the installed GnuCOBOL banner and native execution capability, record the
compiler policy and runtime identity, and compile supported batch cases. The
earlier 16/16 compiler-restoration result is a prerequisite receipt, not evidence
that new migration cases compile. Unavailable compile or behavior capability
stays `unavailable`; it cannot become `pass` or a synthetic expected-output run.
Freeze `MigrationValidationProtocol`-equivalent backend/code/fixture pins before
any live patch generation. Base source pins must verify before applying patches.

## Required gates before R2.1/R2.2 handoffs

Write meaningful tests before implementing the new gate:

- Model-authored identity, self-signed human claims, missing roles, reused
  contexts, unapproved decisions, post-review input changes, and hash tampering
  all fail promotion.
- Independent verifier input contains no primary response; generation input
  contains no unrelated cases, hidden labels, mutation provenance, or detector
  outcomes on the oracle track.
- Legacy human review and request/report paths retain their existing behavior.
- Fixtures distinguish the original defect from intended remediation and catch
  unaffected regressions; unavailable capability remains unavailable.
- Backend checks operate on actual staged files, reject unsupported/no-op or
  out-of-scope patches, and retain every failed check and exception.
- Requests and exact captures reconcile by immutable case/track/run key; zero
  pending reviews are reported as completed.
- Successor decision activation is fail closed; non-GO cannot create a
  detector-led request, and excluded cases cannot enter either denominator.

R2.1 freezes only after R1.7 is terminal and review, fixtures, promoted cases,
decision bindings, exact counts, and wave map reconcile. R2.2 then freezes the
Luna/max generation requests/runtime and seals a separate qualification before
live generation.
