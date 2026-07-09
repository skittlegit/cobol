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

(empty)

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
