# Track A chat — items needing a decision (2026-07-12 review)

One real design call (F7). The rest routed to Track A are plain code bugs (no
decision) — listed at the bottom as FYI; they arrive via FLAGS.

## F7 (design) — dead-code reachability treats forest-roots as reachable

`entry_points` (`static_analysis/call_graph.py:133`) marks **every** paragraph
with no incoming PERFORM/GO TO as an entry. So an *isolated dead paragraph*
becomes an entry root and is counted **reachable** — the existing synthetic test
only catches dead *cycles* (each dead node has an incoming edge). This matches
the T1.2 work order as written, but it is **unsuitable as the basis for D6
(dead compliance code) detection**, which is a first-class drift class.

**Decision:** before D6 detection is built, split the two notions —
- true **program-entry roots** (batch main driver / declared entry semantics),
  used for reachability, vs
- **forest roots** (current behavior), exposed separately if still useful.

Not urgent (D6 isn't being built yet), but decide the entry-point semantics
before the D6 task starts, and add a synthetic *isolated* dead-paragraph fixture
to lock it. Owner: Track A. Track down to the D6 work order.

## H6 (governance) — confirm contract-file owners

`.github/CODEOWNERS` omits `tool_types.py`, and `schemas.py` has no Track A
owner even though it is an A/B/C contract. Confirm the intended owners in chat,
then update CODEOWNERS (governance file — don't guess owners).

## FYI — incoming Track A code fixes (no decision, via FLAGS)

- **F5** — qualified-name trace not case-insensitive (`dataflow.py:374` splits
  uppercase `" OF "`/`" IN "`; uppercase the spec *before* splitting).
- **F6** — preprocessor silently drops unterminated `EXEC…END-EXEC` /
  `COPY…REPLACING` at EOF; should raise a structured error (line-fidelity
  invariant).
- **F10** — `fetch_corpora.sh` skips CardDemo when the dir exists without
  checking `HEAD == 59cc6c2`; a stale checkout invalidates line-level fixtures.
