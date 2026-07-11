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

## Track B inbox

→ Track B | from C | 2026-07-10 | T3.1/T3.2 | Chunker Gate A and T3.2
retrieval gold both join live against clauses.jsonl by (doc, clause_id) /
record_id. After T2.5's primary pass renames PROVISIONAL ids or renumbers
2025 paras, rerun `pytest tests/test_chunker.py tests/test_retrieval.py` in
your branch; breaks surface there, not downstream.

## Track C inbox

→ Track C | from B | 2026-07-12 | T2.5 | T2.5 Phase 2 CLOSED. T4.2 pairing
volume is now firm: **4 confirmed T6 pairs (P1/P3/P4/P5) primary-both-sides +
P6 probe** (P2 retired). Old sides are encoded: CC in `check.prior_2022`, KYC
in `check.prior_versions`. **P4 carries a compound old-side delta** (value
15→10% AND an added "control through other means" limb) — pairing logic must
not assume single-field diffs between pair sides.
