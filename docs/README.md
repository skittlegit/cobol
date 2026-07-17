# Documentation Index

## Repository-level documents

- [`CONTRACT.md`](CONTRACT.md) — signed cross-track interfaces and evaluation
  contract.
- [`team-workflow.md`](team-workflow.md) — task, branch, review, and integration
  workflow.
- [`../CLAUDE.md`](../CLAUDE.md) — repository invariants, ownership, and commands.
- [`../STATUS.md`](../STATUS.md) — authoritative task state.
- [`../FLAGS.md`](../FLAGS.md) — current cross-track inboxes.
- [`../BACKLOG.md`](../BACKLOG.md) — unscheduled verified work.

## Task records

Every task has exactly one file named
`tasks/T<n>.<n>-work-order.md`. That file contains its specification, accepted
amendments, rubrics, and durable completion evidence. Do not add task-specific
sidecars such as `*-report.md`, `*-note.md`, `*-rubric.md`, `*a-*`, or `*b-*`.

## Reviews and references

- `reviews/` retains ratified contract decisions or unresolved review material
  that is still referenced by a live flag/backlog item.
- `reference/` holds validated historical implementation references that remain
  useful to current code.

Generated smoke runs, superseded handoffs, routing drafts, and resolved
checklists should not remain under `docs/`.
