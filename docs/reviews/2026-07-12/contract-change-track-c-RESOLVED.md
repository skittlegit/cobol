# CONTRACT CHANGE — RATIFIED by Track C (schema owner)

**Date:** 2026-07-12 · **Status:** ratified (the superseded proposal has been
folded into this decision record) · **Effect:** `schemas.py` SCHEMA FREEZE was
broken and **re-frozen** at v2.
`docs/CONTRACT.md` → v1.2. **Affects Tracks A/B/C** (A: consumes only, no edits).

Executed by the integrated T0.3 schema-v2 amendment
(`docs/tasks/T0.3-work-order.md`). No Track B
emitter may target the v1 shape after this lands.

---

## Item 1 (F2) — interprocedural line-to-program binding: **ADOPTED as proposed**

The flat `CodeLocus` cannot say which line lives in which program. For an
MO-3×/MO-6× instance, `programs=[A,B]` + one `line_span` + `line_level=[120,340]`
is unresolvable. That makes **interprocedural localization — the headline
metric — unscoreable**. Not cosmetic; adopt.

Four sub-decisions:

1. **`SourceLocus` / `loci`: adopted.**
2. **Full replace, no compat shim.** A shim keeps the ambiguous flat fields
   alive and reachable, which is precisely the defect. One fixture rewrite is
   cheaper than an ambiguity we have to remember not to use.
3. **`SourceLocus.paragraph` is optional.** D4 stale-reference-data lives in
   WORKING-STORAGE; D2 insertion points need not sit inside a paragraph.
   Convention: populate it whenever the locus does fall in a paragraph.
4. **`file` added now, not deferred.** MO-1× is *definitionally* "the stale
   threshold lives in a copybook constant." Deferring `file` guarantees a
   second freeze break the moment B implements MO-1×. `file=None` means "the
   program's own source"; otherwise the copybook/file the line resolves to via
   Track A's LineMap.

Plus a **one-way validator**: loci spanning >1 distinct program force
`is_interprocedural=True`. (Not the reverse — `is_interprocedural` also covers
cross-*paragraph* single-program cases, per playbook §1E. It stays an explicit
required annotation.)

---

## Item 2 (F1c) — comparator: **BOTH proposed options REJECTED. Option C adopted.**

The proposal assumed `current_value` is flat. It is not — it is **recursive**.
Seven of nineteen records in `clauses.jsonl` are `kind: "composite"` whose
`value` nests further CurrentValue-shaped dicts:

```json
CC-08a → {"kind":"composite","value":{
   "closure_window":  {"kind":"duration_working_days","value":7},
   "penalty_per_day": {"kind":"amount_inr","value":500},
   "day_basis":       {"kind":"enum_set","value":["calendar_day"]}}}
```

Against that data:

- **Option B (hoist `comparator` to top-level) is incoherent.** CC-08a has three
  leaves. Which one would a single top-level comparator describe?
- **Option A (comparator-in-`value` + accessor helper) papers over an untyped
  recursion.** The helper would still shape-sniff, and nothing validates that a
  D5 clause carries a comparator at all — for the one drift class defined
  entirely by `>` vs `>=`.

**Option C — make the recursion explicit and typed; `comparator` and `note` are
fields on every node.** Each leaf *is* a `CurrentValue`. D5 comparator drift
becomes a typed lookup at any depth; MO-5's targeting map becomes genuinely
data-driven ("targeting map is data", the original F1c goal, actually achieved).

`Comparator` literal set, chosen to match B's existing vocabulary so migration
is mechanical: `strictly_greater`, `at_least`, `strictly_less`, `at_most`,
`equal`, `not_equal`.

Composite nodes carry **no** comparator (validator-enforced) — comparators
belong to leaves.

---

## Item 3 (F-C1) — NEW, raised by Track C: composite clauses make D1/D5 unscoreable

**Blast radius beyond the original proposal — flagged deliberately.**

A D1 stale-threshold instance against CC-08a has **three** candidate numbers
(7 working days / ₹500 / calendar-day basis). Nothing in the schema says which
one drifted, so T4.2 cannot score it and MO-1 cannot target it deterministically.
Seven of nineteen clauses are affected.

**Add `DriftInstance.target_path: str | None`** — a dotted path into
`regulation_clause.current_value` (e.g. `"penalty_per_day"`, or `"a.b"` when
nested). `None` for non-composite clauses.

**Required** when the clause's `current_value.kind == "composite"` and
`drift_type ∈ {D1_stale_threshold, D5_boundary_error}`; validator resolves it
and asserts it lands on a non-composite node. Ships with a
`resolve_path(current_value, path) -> CurrentValue` helper that B's emitters
and C's metrics both use.

---

## Blast radius

| Track | What changes |
|---|---|
| **C** | `schemas.py` (v2), `tests/test_schemas.py`, `tests/fixtures/drift_instance_d1_kyc.json`, `docs/CONTRACT.md` → v1.2. T4.2 metric code (not yet written — targets v2 from the start). |
| **B** | `data/regulations/clauses.jsonl`: ~10 `current_value` blocks migrate comparator-in-`value` → typed `comparator` field (CC-10a's `"note":"fortnight"` → `note` field). Mechanical; `tests/test_clauses.py` gates it. T2.2 / T2.5-Phase-3 emitters target v2 — **neither is written yet, which is why this is the cheapest possible moment.** |
| **A** | **None.** Track A consumes DriftInstances; it does not emit them. `tool_types.py` is untouched. |

## Preserved invariants

- **T6 pairing** still rests on struct equality of `code_locus` (CONTRACT.md
  Part 2, B's sign-off note 1). The field list changed; the convention did not.
  B's byte-identical-`code_locus` obligation carries over unchanged to `loci`.
- **D2 insertion-point line convention** (B's sign-off note 2) carries over:
  `line_level` now holds `SourceLineRef`s, still pointing at insertion points
  for D2.
- The seven `drift_type` literals are **unchanged**.
