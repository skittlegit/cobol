# Team Workflow — how the three of us actually work

One repo (`skittlegit/cobol`), one Claude Project with three long-lived chats (**Track A**,
**Track B**, **Track C**), and Claude Code as the implementation hand. This doc is the operating
manual; the *what* lives in your track brief (`docs/track-{a,b,c}-brief.md`), the *specs* in the
playbook (project files), the repo conventions in `CLAUDE.md`.

## The common loop (everyone, every work session)

```
1. OPEN your track chat.
   It runs the session-start protocol: reads STATUS.md, searches sibling chats
   for the task IDs you depend on, and reconciles. Trust its correction if it
   contradicts what you remember.

2. DECIDE in chat.
   [chat] tasks (domain curation, lit review, gate adjudication, design calls)
   happen here entirely — output is a doc or data file you commit.
   [code] tasks: the chat's job is to sharpen the spec if the brief is
   ambiguous, not to write the code.

3. EXECUTE in Claude Code (for [code] tasks).
   cd into the repo and prompt:
      "Read CLAUDE.md and docs/track-X-brief.md. Execute T-n.n.
       Write the gate test first. Stop and ask if you hit a CONTRACT question."
   Claude Code reads CLAUDE.md automatically every session — you never paste
   project context.

4. REVIEW back in your track chat.
   Bring gate results, failures, and any `# DECISION:` comments Claude Code
   left. The chat adjudicates: accept, or refine the spec and re-run step 3.
   Do not hand-patch Claude Code's output silently — fix the spec or fix it
   via Claude Code so the brief stays the source of truth.

5. CLOSE the session.
   Commit (see git rules), paste the updated STATUS.md lines the chat gives
   you into project files, and promote any cross-track deliverable to project
   files ("Promote to project files: yes — consumed by Track X").
```

## Git rules (three people, one repo)

- **Branch per task:** `track-a/T1.1`, `track-b/T2.2`, etc. PR into `master`.
- **Merge bar:** your task's gate test green + all prior gates green (`pytest -x -q`).
- **Commit prefix:** `T1.1: <what changed>` — task IDs make STATUS.md auditable from git log.
- **Ownership = write access.** A owns `ingest/ parser/ static_analysis/ model/run_cobol.py
  tools.py vendor/`; B owns `benchmark/ data/`; C owns `schemas.py rag/ model/(rest) agent/
  eval/ labels/`. You never edit another track's modules — if their code blocks you, flag it
  in your chat as a cross-track issue; the owning track fixes it.
- **Review:** self-merge inside your own modules. Any PR touching `schemas.py`, `tools.py`
  signatures, or `docs/CONTRACT.md` needs a "CONTRACT CHANGE" flag and sign-off from the other
  two chats before merge — no exceptions, this is the seam that keeps three parallel tracks
  from drifting apart.

## Person A — Track A (program analysis & tooling)

Ratio ~80% Claude Code / 20% chat. Sequence: T1.0 scaffold → T1.1 preprocessor+parser →
T1.2–T1.4 graph/dataflow/slicer (T1.5 harness in parallel) → T1.6 tool layer. The chat earns
its keep at the gates: paragraph-fixture disputes, new preprocessor patterns (brief rule 4 —
never patch the grammar, extend the preprocessor and log it), and LineMap edge cases. You are
the critical path: ship each tool incrementally with the regex fallback so B and C never wait
on you. Your Wk-7 obligation: one real tool callable by C's agent (the seam test).

## Person B — Track B (benchmark, data & domain)

Ratio ~50/50, and the chat half comes *first*: T0.2 taxonomy examples and the CardDemo-vs-KYC
fit decision, then T2.1 clause curation (rbi.org.in primary text, ≥15 clauses) and T2.5 real
seed — all [chat], producing `docs/` and `data/regulations/` files. Only then does Claude Code
work start: T2.2 `mutate.py` (the probe-classifier anti-gaming gate is yours to keep green),
T2.3 CLI, T2.6 splits. T2.4 plausibility is hybrid: Claude Code runs the LLM-judge batch, you
spot-check the 50-item sample in chat. Start T2.5 early and keep it running in the background —
it's domain-heavy, parallelizes with everything, and feeds Track C's T6 task.

## Person C — Track C (agent, RAG & eval) + Lead

Day one is [chat]: materialize `docs/CONTRACT.md` (tool half copied from the Track A brief —
already unblocked), then T0.6 lit review with live web search. Then Claude Code: T0.3
`schemas.py`, the `StubToolLayer`, T3.1–T3.6 in order — everything against the stub so Track A
never blocks you; swapping stub→real at Wk 7 must be a one-line change. **Lead duties layered
on top:** you call the integration checkpoints from STATUS.md, you propagate CONTRACT CHANGE
flags into all three chats, and you own the M0-close call once T0.2 (B) and T0.6 (you) land.

## Failure modes to watch (learned already)

1. **Stale cross-track beliefs** — Track C thought T0.4 was blocked after Track A had fixed
   the tool contract. The session-start protocol exists because of this; don't skip it.
2. **Silent divergence from the brief** — if Claude Code's output doesn't match the spec, the
   bug is in one of them; decide which in chat and fix *that*, don't paper over it in code.
3. **STATUS.md rot** — it's only authoritative if updated every session. Thirty seconds of
   pasting beats an hour of three chats re-deriving reality.
4. **Contract creep** — "small" signature tweaks in `tools.py` or `schemas.py` are how the
   tracks stop composing. The CONTRACT CHANGE flag is cheap; a Wk-10 integration failure isn't.
