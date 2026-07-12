# FLAGS — cross-track message ledger

Append-only inbox per track. Rules:

1. A flag rides the commit of the deliverable that caused it (same-commit rule,
   like STATUS lines).
2. Format: `→ Track X | from Y | YYYY-MM-DD | T-n.n | message`.
3. The receiving track deletes its own entries once acknowledged in its chat
   (each track edits only its own inbox).
4. Session-start protocol includes reading this file alongside STATUS.md.
5. Urgent mid-session CONTRACT CHANGEs still get relayed directly in chat; this
   file is the async path, not the emergency path.

## Track A inbox

→ Track A | from C | 2026-07-07 | T0.4 | CONTRACT.md v1.1 reproduces your
committed ToolLayer Protocol verbatim. Two deltas beyond your A1/A2 flag were
picked up from tool_types.py and folded in as part of A1: run_cobol inputs typed
`RunInputs | None`, search_regulations returns `list[RegSearchHit]`. If either
was unintentional, raise a CONTRACT CHANGE.

→ Track A | from B | 2026-07-12 | T1.0/T1.1/T1.3 | External review — 3 code bugs
(no decision needed): (F5) qualified-name trace not case-insensitive —
`dataflow.py:374` splits uppercase " OF "/" IN " then uppercases, so
`errmsgo of cosgn0ao` → 0 sites vs 2 uppercase; normalize spec to upper BEFORE
splitting. (F6) preprocessor drops unterminated EXEC…END-EXEC / COPY…REPLACING
at EOF (masked output, 0 masked_spans, no error) — raise a structured error;
line-fidelity invariant. (F10) fetch_corpora.sh skips CardDemo when the dir
exists without checking HEAD == 59cc6c2. Full detail + the F7 entry_points/D6
design call: docs/reviews/2026-07-12/chat-track-a.md.

## Track B inbox

→ Track B | from A | 2026-07-12 | T1.4 | T1.4 done. T2.2 now waits only on T1.5.

## Track C inbox

→ Track C | from B | 2026-07-09 | T2.1 | RE-ANCHOR: the CC corpus document is now the
RBI (Commercial Banks – CC/DC: Issuance and Conduct) Directions, 2025 (2022 MD repealed
2025-11-28); KYC bridge = 2025 para 90 (supersedes the earlier "clause 29" message).
Still two documents; chunk to clause_id granularity in data/regulations/clauses.jsonl.
2025 para numbers are secondary-mapped — primary-PDF confirmation is T2.5's first step.

→ Track C | from B | 2026-07-09 | T0.6 | IndiaFinBench acknowledged + assessed: text-only
RBI/SEBI QA (78 temporal items), no code axis — cite in related work, novelty cell intact.
Also add arXiv 2605.23497 (German statutory temporal QA: pre/post-amendment versioned
questions) to the T7.5 skeleton — nearest neighbor to T6's framing, still no code axis.

→ Track C | from A | 2026-07-12 | T1.4 | M1 passed; slicer live. Week-7 seam test can
target `slice_on`/`trace_variable` as the first real tool swap.

→ Track C | from B | 2026-07-12 | T2.5 | T2.5 Phase 2 CLOSED. T4.2 pairing
volume is now firm: **4 confirmed T6 pairs (P1/P3/P4/P5) primary-both-sides +
P6 probe** (P2 retired). Old sides are encoded: CC in `check.prior_2022`, KYC
in `check.prior_versions`. **P4 carries a compound old-side delta** (value
15→10% AND an added "control through other means" limb) — pairing logic must
not assume single-field diffs between pair sides.

→ Track C | from B | 2026-07-12 | T3.2 | External review — code (no decision):
(F8) hybrid retrieval returns score=0.0 — `index.py:226` builds Hit(chunk, 0.0)
in `hybrid` mode though `fused` is RRF-ranked; have reciprocal_rank_fusion also
return the RRF score and pass it through. SEPARATELY, a CONTRACT CHANGE proposal
(F2 interprocedural CodeLocus/Labels + F1c comparator) needs Track C sign-off
before T2.2 / T2.5-Phase-3 emit interprocedural data:
docs/reviews/2026-07-12/contract-change-track-c.md.
