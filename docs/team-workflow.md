# Team Workflow

This repository uses three permanent implementation tracks and task-scoped
work orders. Git is the bridge between planning/review chats and code
execution: decisions reach an executor through committed files, and results
reach reviewers through committed branches.

## Canonical records

- `STATUS.md` is the authoritative task-state ledger.
- `FLAGS.md` is the current cross-track inbox; it is not a history file.
- `BACKLOG.md` contains verified but unscheduled work.
- `docs/tasks/T<n>.<n>-work-order.md` is the single specification and durable
  evidence record for that task.
- `docs/CONTRACT.md` is the signed cross-track interface.
- `CLAUDE.md` contains repository-wide invariants, ownership, and commands.
- `docs/reviews/` retains only unresolved review input or ratified decisions
  whose rationale is still needed. Draft routing notes and completed checklists
  are folded into the affected work order, flag, backlog item, or contract
  decision and then removed.

There are no track briefs or task sidecars. Corrective phases, rubrics,
reports, and amendments belong in the one canonical work order. Generated
evidence may update a clearly delimited section of that file.

## Precedence

For task execution: the task work order wins over `CLAUDE.md`. For shared
interfaces, `docs/CONTRACT.md` wins unless a ratified CONTRACT CHANGE says
otherwise. `STATUS.md` alone decides whether a task is todo, wip, blocked, or
done. If these records conflict, stop and reconcile them rather than choosing
silently.

## Work loop

1. Read `STATUS.md`, `FLAGS.md`, `BACKLOG.md`, `CLAUDE.md`, and the task's
   canonical work order.
2. Resolve design/domain questions in the owning track chat and commit the
   result into that work order before implementation.
3. Execute with: `Read CLAUDE.md and docs/tasks/T<n>.<n>-work-order.md. Execute.`
4. Write the gate first, implement within the owning track, and stop on a
   contract question or an unresolvable specification conflict.
5. Update the task's `STATUS.md` entry in the same commit as its implementation
   or evidence. Add cross-track flags only when another track has an action or
   must acknowledge a changed interface.
6. Review the diff and gates from the committed branch. Fold accepted
   corrections back into the same work order; do not create `a`, `b`, repair,
   handoff, rubric, or report variants.
7. Remove acknowledged flags and delete intermediate generated artifacts once
   their canonical evidence is recorded.

## Branching and integration

- Permanent branches are `master`, `track-a`, `track-b`, and `track-c`.
- Work on the owning `track-*` branch and merge reviewed changes into `master`.
- Use merge commits for cross-track integration; do not rebase shared permanent
  branches.
- Commit subjects begin with the task ID, for example
  `T3.2: refresh retrieval evidence`.
- Do not push implementation commits directly to `master`.
- The merge bar is the task gate plus all relevant prior gates. Run the full
  offline suite unless the work order specifies a narrower environment gate.
- `STATUS.md` is shared, but a track edits only its own task lines. Reconcile
  concurrent changes by preserving both tracks' valid updates and keeping one
  line per task.

## Ownership

- Track A owns parser, preprocessing, static analysis, runtime harness, and
  ToolLayer implementation.
- Track B owns regulation curation, benchmark mutation/build/judging, and
  benchmark splits.
- Track C owns frozen schemas, RAG, verification, agent orchestration, and
  evaluation.
- Shared governance/configuration changes require coordination. Never change
  another track's owned module as a convenience; flag the owner.

## Contract changes

Any semantic change to `schemas.py`, ToolLayer signatures, or
`docs/CONTRACT.md` is a CONTRACT CHANGE. Record the proposal, obtain the
required cross-track sign-offs, update the contract and affected work orders,
and then implement. Documentation cleanup may relocate references but must not
silently alter contract semantics.

## Common failure modes

- Uncommitted work orders or branches are invisible to the other half of the
  workflow.
- Mirrored briefs and sidecars drift; one canonical file per task prevents it.
- A green structural gate can still miss the task's purpose; encode
  purpose-level minima in the work order and tests.
- Stale `STATUS.md` or resolved `FLAGS.md` entries make completed work appear
  blocked.
- Temporary judge/checkpoint outputs are not deliverables; retain only the
  canonical artifact set named by the work order.
