# Team Workflow — how the three of us actually work

One repo (`skittlegit/cobol`), one Claude Project with three long-lived chats
(**Track A**, **Track B**, **Track C**), and Claude Code as the implementation
hand. This doc is the operating manual; the _what_ lives in your track brief
(`docs/track-{a,b,c}-brief.md`), repo conventions in `CLAUDE.md`, chat-side
rules in the project instructions.

**The one mental model that matters:** the track chats and Claude Code are
completely disconnected — no shared state, no live link. The bridge is you plus
git, in both directions: chat decisions reach Claude Code **only as committed
files** (work orders); Claude Code's results reach the chat **only as pushed
branches** (the chat clones and reviews). Nothing is ever pasted between them.

## Where things live (no mirrors, ever)

- **Repo = canonical home for everything with a path:** specs and decision
  records → `docs/`, work orders → `docs/tasks/`, code →
  `src/cobol_archaeologist/…`, data → `data/`. **Committing IS the promotion** —
  a deliverable is real when it's in git, and only there.
- **Project files hold exactly three things:** the master playbook, the pipeline
  doc, and `STATUS.md`. Nothing else — mirrored copies of repo docs drift and
  are forbidden.
- **Chats read the repo directly** (clone/fetch) when they need a brief,
  contract, work order, or another track's code. Never paste repo content into a
  chat by hand.
- **Commits land silently.** No other chat notices a commit until its next
  session-start protocol. Anything urgent — a CONTRACT CHANGE, an unblock — you
  carry as a one-line note into the affected track chat; the committing chat's
  handoff line tells you when ("flag to Track X").

## Document precedence (memorize)

For a given task: **work order (`docs/tasks/T<n>.<n>.md`) > track brief >
CLAUDE.md**. Cross-track interfaces: `docs/CONTRACT.md` wins over everything
except an explicit CONTRACT CHANGE decision. Chat memory loses to all of the
above.

## The common loop (everyone, every work session)

```text
1. OPEN your track chat.
   It runs the session-start protocol (STATUS.md + sibling-chat search +
   reconcile). Trust its correction if it contradicts what you remember.

2. DECIDE in chat.
   [chat] tasks (domain curation, lit review, gate adjudication, design calls)
   happen here entirely — output is a doc/data file destined for the repo.
   [code] tasks: say "prepare T-n.n". The chat verifies current repo state and
   authors the WORK ORDER: current state → objective → deliverables →
   gate-first → stop conditions → out of scope. (Template: docs/tasks/T1.0.md.)

3. COMMIT the work order to docs/tasks/T<n>.<n>.md — before execution, always.
   Uncommitted work orders don't exist; pasting into Claude Code leaves no
   audit trail and makes review unverifiable.

4. EXECUTE in Claude Code:
      "Read CLAUDE.md and docs/tasks/T<n>.<n>.md. Execute."
   That is the entire prompt. Claude Code writes the gate test first, works on
   the owning permanent branch track-<a|b|c>, leaves # DECISION: comments at ambiguities,
   and STOPS on contract questions or work-order/brief conflicts. If it stops
   with a design question, the answer comes from your track chat — not ad hoc
   in the terminal.

5. PUSH the branch, then in your track chat: "review T-n.n".
   The chat clones the branch, runs the gate tests itself, checks the diff
   against the work order, and adjudicates every # DECISION: comment.
   Verdict: merge / fix-via-new-instruction / spec-was-wrong (fix the work
   order or brief, re-run step 4 — never hand-patch silently).

6. CLOSE the session.
   Merge (if green). Every chat deliverable ends with its handoff line —
   "Commit to: <repo path>" plus "flag to Track X" if another chat must be
   told — act on both. Paste the updated STATUS.md lines into project files.
   Fold durable learnings from the work order back into the track brief if
   they generalize.
```

## Git rules (three people, one repo)

- **Permanent branch per track** (`track-a`, `track-b`, `track-c`), with reviewed
  PRs into `master`; merge bar = this task's gate green **plus all prior gates
  green** (`pytest tests/ -x -q`).
- **Commit prefix** `T1.1: <what changed>` — makes STATUS.md auditable from git
  log.
- **Ownership = write access** (module→track map in CLAUDE.md). Never edit
  another track's modules; if their code blocks you, flag it in your chat as a
  cross-track issue.
- **CONTRACT CHANGE:** any PR touching `schemas.py`, `tools.py` signatures, or
  `docs/CONTRACT.md` needs the flag raised and sign-off from the other two chats
  before merge. No exceptions — this seam is what keeps three parallel tracks
  composable.

## Person A — Track A (program analysis & tooling)

~80% Claude Code / 20% chat. Sequence: T1.0 scaffold (work order committed) →
T1.1 preprocessor+parser → T1.2–T1.4 graph/dataflow/slicer (T1.5 harness in
parallel) → T1.6 tool layer. The chat earns its keep at gates: paragraph-fixture
disputes, new preprocessor patterns (never patch the vendored grammar — extend
the preprocessor and log it in `docs/preprocessor-notes.md`), LineMap edge
cases. You are the critical path: ship each tool incrementally with the regex
fallback so B and C never wait. Wk-7 obligation: one real tool callable by C's
agent (the seam test).

## Person B — Track B (benchmark, data & domain)

~50/50, chat half first: T0.2 taxonomy examples + the CardDemo-vs-KYC fit
decision, then T2.1 clause curation (rbi.org.in primary text only, ≥15 clauses)
and T2.5 real seed — all [chat], producing `docs/` and `data/regulations/` files
committed straight to the repo (no work order needed for [chat] deliverables).
Claude Code starts at T2.2 `mutate.py` (the probe-classifier anti-gaming gate is
yours to keep green), then T2.3 CLI, T2.6 splits. T2.4 is hybrid: Claude Code
runs the LLM-judge batch, you spot-check the 50-item sample in chat. Start T2.5
now and keep it running in the background — it's domain-heavy, parallelizes with
everything, and feeds Track C's T6 versioned-judgment task.

## Person C — Track C (agent, RAG & eval) + Lead

Day one is [chat]: materialize `docs/CONTRACT.md` (tool half copied verbatim
from the Track A brief §T1.6 — already unblocked), then T0.6 lit review with
live web search. Then Claude Code: T0.3 `schemas.py`, the `StubToolLayer`,
T3.1–T3.6 in order — all against the stub so Track A never blocks you; stub→real
at Wk 7 must be a one-line swap. **Lead duties on top:** call the integration
checkpoints from STATUS.md (Wk 2 M0 · Wk 7 seam · Wk 10 M4 go/no-go · Wk 13 M5 ·
Wk 16 M7), propagate CONTRACT CHANGE flags into all three chats, own the
M0-close call once T0.2 (B) and T0.6 (you) land.

## Failure modes to watch (all already observed or near-missed)

1. **Stale cross-track beliefs** — Track C thought T0.4 was blocked after Track
   A had fixed the tool contract. The session-start protocol exists because of
   this; don't skip it.
2. **Uncommitted state** — a work order refined in chat but not committed means
   Claude Code executes the stale spec; a branch not pushed means the chat
   reviews nothing. If it isn't in git, it didn't happen.
3. **Mirror drift** — a repo doc copied into project files (or pasted into a
   chat) silently goes stale and someone builds against it. One home per
   document; the repo copy wins.
4. **Silent divergence** — output doesn't match the work order? The bug is in
   exactly one of them; decide which in chat and fix _that_. Hand-patching code
   while the spec says otherwise is how the doc set stops being trustworthy.
5. **STATUS.md rot** — thirty seconds of pasting beats an hour of three chats
   re-deriving reality.
6. **Contract creep** — "small" signature tweaks in `tools.py`/`schemas.py` are
   how tracks stop composing. The flag is cheap; a Wk-10 integration failure
   isn't.
