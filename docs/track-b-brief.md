# Track B — Execution Brief (T0.2, T2.1–T2.6)

Benchmark, Data & Domain track. Near-term milestones: close **T0.2** (last M0
blocker on this track), then **M2 — Synthetic v1 + Seed Started**. Later tasks
(T5.1 scale + annotation guidelines, T5.2 freeze + datasheet, T7.3 release) are
out of scope for this brief.

Each task is marked **[chat]** (domain/analysis work done in the Track B chat,
output = a doc committed to `docs/` or `data/`) or **[code]** (implemented via
Claude Code in this repo). Read `CLAUDE.md` first — the locked decisions and
line-number-fidelity rule bind this track too.

## Interfaces this track consumes (do not reimplement)

- `schemas.DriftInstance` — owned by Track C (T0.3). Shape (reference):
  `instance_id`, `regulation_clause` with `doc`, `clause_id`, `version`,
  `effective_date`, `text`, and `current_value{kind, value}`,
  `code_locus{programs, paragraphs, line_span, slice_vars, is_interprocedural}`,
  `drift_type (D1…D7)`, `labels{program_level, paragraph_level, line_level}`,
  `gold_rationale`, `provenance{source, base_program, mutation}`.
- `parser`, `slicer`, `compile_check`/`run_cobol` — owned by Track A
  (T1.1–T1.5). Until they land, develop against the corpus with the spike-grade
  regex fallback; never block on Track A.

## Drift taxonomy (v0, to be locked by T0.2)

- **D1** stale parameter/threshold · **D2** missing rule · **D3**
  contradictory/over-permissive
- **D4** stale reference data · **D5** boundary/comparator error (`>` vs `>=`,
  off-by-one)
- **D6** dead compliance code (unreachable) · **D7** conformant (negative class)

---

## T0.2 — Lock taxonomy v1 with real CardDemo examples **[chat]** ← next task

For each class D1–D7, find one concrete locus in CardDemo (program, paragraph,
line span) that either exhibits the pattern or is the natural host for its
mutation. Deliverable: `docs/T0.2-taxonomy-examples.md` — per class: the code
excerpt (≤15 lines), the clause _type_ it maps to, and which mutation operator
would synthesize it.

**Open question this task must answer (raised in Track B chat):** CardDemo is
credit-card servicing; pure-KYC checks (PEP screening, periodic re-KYC) may have
no natural host there. Resolution options to evaluate and decide: (a) widen the
anchor clause set to include RBI credit-card/transaction-reporting clauses that
CardDemo naturally hosts, keeping KYC 2025 for the real-curated seed (T2.5); (b)
host KYC logic in the GnuCOBOL-native runnable base. Whichever is chosen: **flag
as CONTRACT CHANGE if it alters T2.1's clause set scope.**

**Done when:** each of D1–D7 has a real example + the CardDemo-vs-KYC fit
decision is written down with 3 sentences of justification.

## T2.1 — Regulation curation + clause→check map **[chat, domain-heavy]**

From the anchor regulation set (per the T0.2 decision), extract **≥15 clauses**
into `data/regulations/clauses.jsonl`, one record per clause: `doc`,
`clause_id`, `version`, `effective_date`, `text` (verbatim, short),
`current_value{kind, value}` where applicable, `required_check` (one sentence:
what code must do), `candidate_drift_classes`. Pull regulation text from
**rbi.org.in primary sources only**; record the source URL per clause. This file
is the input to mutation targeting (T2.2) and to Track C's chunker (T3.1).

**Done when:** ≥15 clauses with version + effective_date, reviewed once in the
Track B chat.

## T2.2 — Mutation operators **[code]** — `src/cobol_archaeologist/benchmark/mutate.py`

Each operator has this shape:

```text
(conformant_program, clause_record)
  -> MutationResult{mutated_text, drift_type, labels, provenance}
```

All edits are **line-count-preserving where possible**; labels are line numbers
in the _original_ coordinate system.

- **MO-0 / D7:** benign edits on conformant code. Includes renames, reflow,
  non-regulated literal changes, and comment rewording. This is mandatory for
  anti-gaming and anti-memorization.
- **MO-1 / D1:** replace a regulated numeric literal with an outdated value.
- **MO-2 / D2:** delete the IF branch or PERFORM implementing a required check.
- **MO-3 / D3:** invert a comparator or remove a blocking branch.
- **MO-4 / D4:** remove or alter a hardcoded list/condition-set entry.
- **MO-5 / D5:** swap `>`/`>=` or `<`/`<=`, or shift a boundary by 1.
- **MO-6 / D6:** wrap a compliance paragraph in an always-false guard.

**Interprocedural variants (required — the headline stratum):** MO-1× threshold
lives in a copybook constant; MO-3× contradiction split across two
paragraphs/programs; MO-6× disabling flag set in a different program than the
guarded code.

Hard requirements: every mutated output must pass `compile_check` (Track A T1.5)
when the base program is GnuCOBOL-compilable, else AST-parse cleanly; every
mutated region is **style-diversified** (LLM paraphrase of surface form, then
re-check) so no operator leaves a syntactic fingerprint; MO-0 must make "was
this file edited" carry zero label information — verified by the
probe-classifier test below.

**Done when:** every operator (incl. MO-0 and × variants) produces a valid
labeled instance on the anchor corpus, and a probe classifier given only
surface-edit features scores at chance on drift-vs-conformant (test in
`tests/benchmark/test_probe.py`).

## T2.3 — Generation pipeline **[code]** — CLI `benchmark-build`

```bash
python -m cobol_archaeologist benchmark-build `
  --clauses data/regulations/clauses.jsonl `
  --corpus data/corpora/carddemo `
  --out data/benchmark/drift_instances.jsonl
```

Balanced sampling across D1–D7 and operators; deterministic given a seed. **Done
when:** ≥200 valid instances.

## T2.4 — Plausibility validation **[code + chat]**

LLM-judge each instance for "looks like real drift a maintainer could have
left"; judge must be a **different model family than the system under test**
(record family + version in the run log). Manual spot-check of a 50-item sample
in the Track B chat. **Done when:** ≥90% of the sample judged plausible;
failures dropped with reasons logged.

## T2.5 — Real-curated seed **[chat, start early — parallel to everything]**

Build instances from regulation changes that actually happened: (a) KYC
2016→2025 replacement (code written to 2016 clauses = genuine drift today; also
the raw material for Track C's T6 versioned-judgment pairs); (b) Basel III
SA/LCR transition (2026–2027 effective dates). Implement the _old_ rule in COBOL
on the runnable base, label per schema with before/after values + effective
dates, `provenance.source = "real_curated"`. **Done when:** first 20 validated
instances in `data/benchmark/seed/`.

## T2.6 — Stratify + balance **[code]**

Tag `is_interprocedural`; balance classes; emit train/dev/test splits + a
distribution table. **Done when:** split files +
`docs/benchmark-distribution.md`.

## Standing rules

1. Labels reference original source lines — round-trip through Track A's LineMap
   for anything copybook-expanded. 2. Never hand-edit generated instances; fix
   the operator and regenerate (determinism). 3. Anything that changes the
   DriftInstance shape or the clause-set scope is a **CONTRACT CHANGE — affects
   Tracks A/B/C**; stop and flag it.
