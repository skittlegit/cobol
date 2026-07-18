# FLAGS — cross-track message ledger

Per-track inbox. A receiving track deletes an entry after acknowledging it;
resolved and superseded progress messages do not remain as history here.

## Track A inbox

→ Track A | from C/B | 2026-07-17 | CONTRACT v1.3 FYI | Gate E now splits
artifact-only and attacker-with-bases threat models. No Track A implementation
change: `literal_roundness` is the hard at-chance build gate; the aggregate
surface probe is a mandatory T5.3 baseline. Resolution:
`docs/reviews/2026-07-17/contract-change-gate-e-RESOLVED.md`.

## Track B inbox

_No open flags._

## Track C inbox

→ Track C | from docs audit | 2026-07-18 | T3.2 | The checked-in Gate B table
was generated before T2.5 expanded the frozen retrieval fixture from 1,824
chunks/7 documents to 2,361 chunks/8 documents. The report generator now
updates the canonical evidence block in `docs/tasks/T3.2-work-order.md`. Install
the model extra and rerun `python -m cobol_archaeologist.rag.index`; T3.3 waits
for the refreshed bar.

→ Track C | from A | 2026-07-13 | T1.6 | `RealToolLayer` is
constructor-swappable for the Track C stub. Read the consumer-semantics register
in `docs/tasks/T1.6-work-order.md` before the seam test; it defines sentinel and
truncation semantics beyond structural typing. `search_regulations` remains
Track C's implementation responsibility.

→ Track C | from A | 2026-07-17 | T1.2 | The reachability correction is in
`static_analysis/call_graph.py`: entry and forest-root semantics are separate,
and reachability traverses `edge_kind="fallthrough"`. D6 detection must consume
`forest_roots` plus `reachable_from`, not `entry_points`, which now means the
single true program entry. The T1.2/T1.6 work orders record the fall-through
and ENTRY-verb limitations. Track C should also add `schemas.py` ownership in
its next CODEOWNERS change.

→ Track C | from B | 2026-07-15 | T2.5 | The real-curated seed at
`data/benchmark/seed/real_curated.jsonl` contains 21 instances and five intact
verdict-flipping T6 pairs for T4.2. P2 was retired on primary evidence; P6 is a
citation-axis probe rather than a verdict-flipping pair.

→ Track C | from B | 2026-07-15 | T2.2 | The balanced anti-gaming probe is
`data/benchmark/probes/t2.2_surface_probe.jsonl` (50 drifted + 50 MO-0,
AUC 0.50). Reuse its six-feature contract at T5.3/T5.5.

→ Track C | from B | 2026-07-17 | M2 CLOSED (RE-EVIDENCED) | The corrected
catalogue has 594 compiled rows and distinct D1–D6 mutations 13/6/5/4/12/7.
Current Luna/OpenAI/high evidence is 50/50 on the stratified sample and 557/594
(93.77%) raw on the full set; final drop policy is 562 accepted / 32
implausible / 0 unsure with five logged overrides and 15/15 human agreement.
Corrected v1-pre train/dev/test = 297/106/180; all purpose gates pass. Track C
may consume `data/benchmark/v1-pre/` and begin headline evaluation.
