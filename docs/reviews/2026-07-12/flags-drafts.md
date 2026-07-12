# FLAGS drafts — ready-to-paste routing for code + deferred items

Paste these into `FLAGS.md` under the right inbox. **Caveat on FLAGS rule 1**
(a flag "rides the commit of the deliverable that caused it"): these are
review-driven and don't ride a deliverable commit. Two clean options:
1. Paste now as advisory flags (pragmatic — the review *is* the trigger), or
2. Keep them in this file as a backlog and attach each to the commit that fixes
   it. Pick per your team's tolerance; the text is identical either way.

---

## → Track A inbox

```
→ Track A | from B | 2026-07-12 | T1.1/T1.3/T1.0 | External review, 3 code bugs
(no decision): (F5) qualified-name trace not case-insensitive — dataflow.py:374
splits uppercase " OF "/" IN " then uppercases, so `errmsgo of cosgn0ao` → 0
sites vs 2 for uppercase; normalize the spec to upper BEFORE splitting. (F6)
preprocessor drops unterminated EXEC…END-EXEC / COPY…REPLACING at EOF (masked
output, 0 masked_spans, no error) — raise a structured preprocessing error;
line-fidelity invariant. (F10) fetch_corpora.sh skips CardDemo when the dir
exists without checking HEAD == 59cc6c2 — a stale checkout silently invalidates
line-level fixtures. Design call (F7, entry_points / D6) is in
docs/reviews/2026-07-12/chat-track-a.md — chat, not code.
```

## → Track C inbox

```
→ Track C | from B | 2026-07-12 | T3.2 | External review: (F8) hybrid retrieval
returns score=0.0 — index.py:226 builds Hit(chunk, 0.0) in `hybrid` mode though
`fused` is RRF-ranked; ordering is right but RegSearchHit.score can't feed
thresholds. Have reciprocal_rank_fusion also return the RRF score and pass it
through. SEPARATELY: a CONTRACT CHANGE proposal (F2 interprocedural CodeLocus/
Labels + F1c comparator) is in docs/reviews/2026-07-12/contract-change-track-c.md
— needs Track C sign-off before T2.2 / T2.5-Phase-3 emit interprocedural data.
```

---

## Deferred (no single owner — backlog, not a FLAG)

- **F1b (T2.2 prep, B):** add MO-4 + MO-3×/MO-6× coverage and normalize
  `MO-1x`→`MO-1×` in clauses.jsonl when T2.2 authoring resumes (blocked on T1.5).
- **F9 (packaging):** move runtime assets (grammar, regulation data) under the
  package or declare package-data so a built wheel isn't empty.
- **H2 (all):** one sanctioned `ruff format` sweep — large cross-track diff,
  coordinate.
