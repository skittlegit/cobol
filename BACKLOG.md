# BACKLOG — deferred technical debt & future work

Verified work that is deliberately unscheduled or postponed. This is separate
from the authoritative task ledger in `STATUS.md` and the cross-track inboxes
in `FLAGS.md`.

An item leaves this file when it becomes a canonical work order or when the
change that resolves it is committed. Resolved history remains available in
Git and the affected work orders; it is not duplicated here.

Session-start protocol: skim this alongside `STATUS.md` and `FLAGS.md`.

Format: **ID** — title · source · owner · trigger.

## Open

**M8 — post-release detector improvements** · source: M4 configuration-1
NO_GO and configuration-2 hard stop · owners: A/B/C · trigger: M7 submission
and release complete.

M8 is a future improvement phase, not unfinished M4 work. It cannot change the
recorded M4 result, and it does not block M5 or M7. After the trigger, promote
accepted workstreams into separate canonical `T8.x` work orders before any
implementation or provider spend.

Candidate workstreams:

1. **New detection-method hypothesis (C):** improve verified coverage and
   interprocedural reasoning through better evidence planning, tool selection,
   or retrieval. Do not loosen no-unverified-emission, verifier thresholds,
   evidence minima, or anti-shortcut rules merely to increase answer rate.
2. **Configuration-3 evaluation (B/C):** only after the method hypothesis is
   written. Freeze the model, effort, prompts, budgets, sample, row IDs,
   validity gates, and success bars before smoke; preserve M4 configuration 1
   as the comparison of record.
3. **Impact, performance, and caching profile (A/C):** measure tool latency,
   repeated parsing/retrieval, per-hunt observation allocation, and
   interprocedural bottlenecks against the released on-prem bundle before
   optimizing them.
4. **Migration reconsideration (A/C):** reactivate T6.1-T6.4 only if a new
   detector crosses a predeclared utility bar that makes an equivalence
   showcase meaningful.
5. **Optional UI reconsideration (C):** reactivate T7.4 only after detector
   utility is established and the released CLI/MCP workflows identify a
   concrete user need.

M8 closes only through ratified `T8.x` work orders and valid evidence. A
disappointing measurement remains a result, not permission for iterative
post-result guard or threshold tuning.
