# Pull Request

<!-- Title: [T<n>.<n>] short description, or list tasks in this integration. -->

## Task(s)

- Task ID(s):
- Track / source branch: <!-- track-a / track-b / track-c -->
- Work order(s): `docs/tasks/T<n>.<n>-work-order.md`
  <!-- link if [code] task -->

## What this does

<!-- One or two sentences. What changed and why. -->

## STATUS.md

This PR carries each task's ledger line at its new state, in the same commits
rather than as a follow-up:

    T<n>.<n> | <state> | <track> | <artifact repo path>

## Acceptance ("Done when...")

<!-- The playbook/work-order acceptance criteria, and how this PR meets them. -->

## Contract impact

- [ ] **CONTRACT CHANGE** — touches `schemas.py` (T0.3) or `docs/CONTRACT.md`
      (T0.4). CODEOWNERS routes it to the Lead and other tracks. After merge I
      will flag the other track chats, since merging does not notify them.
- [ ] No contract impact.

## Review

Reviewer: clone this pushed branch and run the gate tests locally. Do not review
from pasted output. Approval must come from a different track because GitHub
blocks self-approval.

- [ ] Cloned the branch and ran the relevant gate tests; they pass.
- [ ] Source branch is current with `master` (`git merge origin/master`, no rebase).
- [ ] Will merge with a **merge commit**.
