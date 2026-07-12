# Branching & pull-request workflow

Four permanent branches. None of them are ever deleted.

- `master` — protected integration branch. No direct pushes; changes land only
  through a reviewed PR.
- `track-a` — Program Analysis & Tooling — **@twiswiz**
- `track-b` — Benchmark, Data & Domain — **@skittlegit** (also Lead)
- `track-c` — Agent, RAG & Evaluation — **@ankitaww**

Each track works on its own branch and pushes there directly. When a batch of
work is ready, the track opens a PR from its branch into `master`. Because every
track has its own branch, two people are never pushing to the same branch.

## Day to day

    git switch track-b && git pull        # your branch
    # ...work, commit (STATUS.md line rides these commits: wip -> done/ready)...
    git push

Edit only your own tasks' lines in `STATUS.md`. To pull in others' merged work,
**merge, don't rebase**. Force-pushes are blocked on track branches:

    git switch track-b && git merge origin/master

## Integrating to master

- Open a PR `track-x -> master` and fill in the template.
- One approval from **another** collaborator is required. GitHub blocks
  self-approval, so integration always gets a second pair of eyes from a
  different track.
- Merge with a **merge commit**, not squash or rebase. A long-lived branch that
  is squash-merged diverges from `master`: its commits never land in `master` as
  themselves, so the next merge re-proposes them and you get phantom conflicts.
  Merge commits keep the track branch reusable forever.
- The branch is **not** deleted after merge. Keep working on it.

## Protections

Rulesets enforce these protections:

- `master`: no direct push, no force-push, no deletion, PR plus one approval,
  resolved threads, and merge-commit only.
- `track-a/b/c`: no deletion and no force-push. Normal pushes are allowed
  because that is how you work on them.

Force-push is blocked on track branches deliberately. It stops an accidental
history wipe on a shared long-lived branch. The cost is that you cannot rebase
your own branch. Use `git merge origin/master` to stay current. If a track
genuinely needs to rebase, drop the `non_fast_forward` rule from the track
ruleset.

## The STATUS.md conflict tax

All three track branches edit the one `STATUS.md`. When two tracks change
**adjacent** lines and both merge into `master`, Git conflicts there. It
auto-merges fine when the edited lines are far apart. The ledger is ordered by
task ID, which interleaves tracks (T0.1=B, T0.3=C, T0.5=A), so some adjacency is
unavoidable.

Every such conflict resolves the same way: each track only touches its own
lines, so take mine for my lines and theirs for theirs. If it gets painful,
grouping the ledger by track instead of by ID removes most of it, at the cost of
ID-ordered readability.

## Claude Code

Claude Code executes a work order and pushes to the relevant track branch, never
`master`. Integration to `master` is the reviewed PR step, done by a human after
cloning the branch and running the gates. No branch-protection bypass is needed
because Claude Code only writes to track branches.
