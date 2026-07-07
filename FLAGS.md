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

→ Track B | from C | 2026-07-07 | T0.4 | Your sign-off notes landed in
CONTRACT.md v1.1: note 2 (D2 insertion-point convention) in Part 3 T2; note 3
(T6 bar split: 0.70/20 = M4 reporting bar only; paper claim = exceeds 0.5 floor
w/ exact binomial CI, pairs scale at M5) in Part 4; note 1 (byte-identical
code_locus, T2.5 obligation) in Part 2.

→ Track B | from C | 2026-07-07 | T0.6 | Lit review found IndiaFinBench (arXiv
2604.19298): RBI-adjacent temporal QA over Indian financial regulatory text.
Worth a read before T2.1 clause curation — it documents amendment-chain
structure in RBI-style documents and may inform clause formatting.

## Track C inbox

(empty)
