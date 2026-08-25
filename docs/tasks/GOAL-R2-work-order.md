# GOAL-R2 work order - migration evaluation and M5 release close

**Owners:** Track A / Track C  
**State:** ready after GOAL-R1 freezes the detector decision  
**Projected remaining usage:** approximately 40 weekly-quota percentage points  
**Depends on:** GOAL-R1, T6.1, and the implemented T6.2-T6.4 offline gates  
**Canonical outputs:** sealed migration runs, validation ledger,
`data/migration/report.{json,md}`, T5.5/M5 analysis, and final release records

## Outcome

Run the isolated migration agent, validate every generated patch, publish the
non-pooled detector-led and oracle-assisted results, and close T5.5/M5 and the
release record without erasing any prior M4 evidence. UI/T7.4 remains deferred.

## Estimated remaining 40-point allocation

| Phase | Planning points | Required result |
|---|---:|---|
| Freeze eligible rosters and requests | 6 | Detector/oracle identities and denominators reconcile |
| T6.2 live migration generation | 13 | Every eligible case has a sealed patch or abstention |
| T6.3 equivalence and safety validation | 11 | Every patch has a fail-closed terminal verdict |
| T6.4 migration report | 6 | Machine and narrative reports reconcile |
| T5.5/M5 and release close | 4 | Final decision and project records are frozen |

The allocation is an estimate, not a termination rule.

## Execution

1. Validate the GOAL-R1 detector freeze, T6-v2 20-pair / 40-side manifest, and
   migration runtime snapshot. Freeze two disjointly labeled rosters:
   detector-led cases from verified detector findings and oracle-assisted
   cases from frozen oracle findings. Never pool them.
2. Materialize exact one-case Luna/max requests in per-case staging
   directories. Prompts expose only the authorized source, verified finding,
   allowed patch scope, and required output contract; no gold label, mutation
   provenance, hidden result, unrelated case, credentials, or git history is
   model-visible.
3. Run T6.2 with at most three independent tasks concurrently. Each eligible
   case must end in one exact sealed patch proposal or one explicit abstention.
   Preserve source inputs, request/final hashes, task events, tool logs, usage
   limitations, and interruption/resume evidence.
4. Apply proposals only to disposable per-case staging copies. T6.3 must check
   source scope, parser integrity, call graph/dataflow/slice consistency,
   intended behavior, unaffected regressions, copybook fan-out, and clean
   application to the frozen source hash. Use pinned GnuCOBOL compile/execution
   for supported batch cases when an authorized runtime provides it. If the
   compiler remains unavailable, report that capability gap; never convert it
   to a pass. Keep CICS limitations explicit.
5. A generated patch that fails validation remains a measured failure. Repair
   orchestration, staging, validator, or reproducibility defects and replay;
   do not manually improve the model patch or discard the case. Detector-led
   execution occurs only when the detector utility gate permits it;
   oracle-assisted evaluation still runs as a separately labeled upper bound.
6. Build T6.4 with exact eligible/evaluated denominators and patch,
   abstention, apply, parse, compile, intended-test, regression, affected-line,
   class, stratum, and capability results. Re-hash every narrative claim to
   machine-readable evidence and report unavailable Luna telemetry as
   `not_recorded`.
7. Complete T5.5/M5 and T7.5 from the frozen detector and migration decisions.
   Update `DATASHEET.md`, `STATUS.md`, `FLAGS.md`, and the final release record.
   Preserve configuration 1's `NO_GO`, configuration 2's smoke stop,
   configuration 3's smoke outcome, and the successor result as distinct
   auditable evidence.

## Self-healing and stop rules

- Checkpoint and replay after every sealed case; resume incomplete run keys.
- Isolate malformed finals and interrupted attempts, retry them with fresh
  identities, and never count an unvalidated replacement.
- Diagnose and repair failed infrastructure, schema, hash, apply, validator,
  report, or reconciliation gates; rerun the affected deterministic checks
  before handoff.
- The projected 50 points do not stop an in-progress repair, retry,
  validation, or report reconciliation. Stop only when the work order has a
  clean terminal outcome and no broken staging state.
- Self-healing does not erase abstentions or failed patches, relax safety
  gates, merge detector and oracle results, fabricate compiler/provider
  evidence, or change the measured detector decision.

## Completion handoff

This order is complete when T6.2-T6.4, T5.5/M5, and T7.5 each have a terminal
auditable state; all reports and manifests reconcile; all active non-UI flags
are cleared or explicitly terminal; and the release record states what is and
is not supported. No UI work is authorized by this order.
