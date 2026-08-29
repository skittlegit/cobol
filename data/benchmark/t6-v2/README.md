# T6-v2 preparation area

This directory is **not an evaluation split yet**. It contains:

- immutable byte-level references to the nine intact, independently reviewed
  T6 pairs already present in `data/benchmark/v1/test.jsonl`; and
- eleven new P3/P4/P5 pair design specifications with byte-pinned COBOL
  fixtures, sealed label proposals, and a coordinator-held sequential blind
  release queue. Their labels still require human-primary review, independent
  verification, and adjudication where reviewers disagree.

The candidates are new designs, now materialized under `candidates/`. None
restores the eight candidates excluded from v1 adjudication. The manifest pins
all fixture, proposal, packet, and response-schema bytes. The schema fixes every candidate to
`candidate_unreviewed`, null review fields, `eligible_for_evaluation: false`,
and `development_use_prohibited: true`. Therefore the current eligible count is
9, not 20, and `evaluation_ready` remains false.

Human reviewers must follow `review/README.md`; they receive exactly one opaque
source envelope at a time and must not receive the full queue, canonical source
map, or sealed `candidates/pair_proposals.jsonl` artifact. Offline pair
unlinkability is procedural, not cryptographically guaranteed.

Run the focused integrity gate with:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_t6_v2.py -q
```

Promotion requires a later, separately reviewed freeze artifact. Do not edit
this preparation manifest to simulate that promotion; add the primary-review,
verification, and adjudication records and produce a new hashed freeze.
