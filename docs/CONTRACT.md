# CONTRACT.md — Cross-track interface contract (T0.4)

**Version:** 1.0 · **Status:** proposed — awaiting sign-off from Tracks A and B
**Governs:** the tool I/O boundary (Track A implements, Track C consumes) and
the evaluation metrics + targets (Track C implements, Tracks A/B build toward).
Changes after sign-off are **CONTRACT CHANGEs** and must be flagged to all
three tracks.

Binding order: this document > track briefs > CLAUDE.md, for the interfaces it
covers. The `DriftInstance` schema itself is frozen separately (T0.3,
`src/cobol_archaeologist/schemas.py`); this document binds against it.

---

## Part 1 — Tool I/O contract

Source: Track A brief §T1.6, reproduced verbatim as the normative signature
set. Track A implements exactly these; Track C's agent and stub layer
(`agent/stub_tools.py`) conform to exactly these. No party redesigns them
unilaterally.

### Structured-return rule (applies to every tool)

Every return is a **pydantic model** carrying **summaries + source pointers**
(program, paragraph, line spans) — never full-file dumps. Any code text is
capped at **~60 lines** with a pointer to fetch more. Every line number in a
public return refers to the **original source file** (via the preprocessor
LineMap), never to preprocessed text.

### Signatures

- `read_paragraph(program, name)` → code, span, and callers/callees summary.
- `read_program(program)` → metadata and paragraph names/spans only.
- `find_callers(program, para)` → `list[NodeRef]`.
- `find_callees(program, para)` → `list[NodeRef]`.
- `trace_variable(var)` → `VariableTrace`.
- `slice_on(var)` → `Slice`.
- `resolve_copybook(name)` → expanded text and a LineMap summary.
- `get_data_layout(record)` → fields, PIC, and REDEFINES tree.
- `grep(pattern)` → matches with `(program, line)`.
- `run_cobol(snippet, inputs)` → `RunResult`.
- `search_regulations(query)` → typed stub raising `NotImplementedError` in
  Track A's `tools.py`; **Track C owns the implementation** (T3.1–T3.3), but
  the signature ships in T1.6 so the contract is complete.

### Stub parity clause

`StubToolLayer` (Track C) must return instances of the **same pydantic return
models** Track A ships in `tools.py`. The Week-7 seam test (stub → real) must
be a one-line constructor swap; any divergence discovered at the seam is a
contract bug, triaged against this document.

---

## Part 2 — Schema bindings consumed by eval

From the T0.3 freeze — restated here because the metrics are defined over
these exact values:

- `drift_type` literals: `D1_stale_threshold`, `D2_missing_rule`,
  `D3_contradictory`, `D4_stale_reference_data`, `D5_boundary_error`,
  `D6_dead_code`, `D7_conformant`.
- Stratification keys: `code_locus.is_interprocedural` (bool) and
  `drift_type`. Every metric below is reported overall **and** per stratum.
- Temporal fields: `regulation_clause.version` + `effective_date` are
  required; T6 pairs are keyed on same `code_locus`, different
  (`version`, `effective_date`).
- System findings are emitted `DriftInstance`-shaped (T3.6) so predictions and
  gold share one schema.

---

## Part 3 — Metrics (definitions of record)

- **T1 Detection** — does this locus conform? Precision / Recall / F1 on a
  class-balanced set (drift = positive; D7 = negative).
- **T2 Localization** — Accuracy@k for k ∈ {1, 3} at program, paragraph, and
  line granularity, plus line-level overlap (predicted lines vs
  `labels.line_level`).
- **T3 Classification** — Macro-F1 over all seven classes D1–D7.
- **T4 Faithfulness** — fraction of findings where BOTH the cited clause is
  correct AND the cited code fact matches `gold_rationale`. **Reported per
  verification tier** (Tier 1 executed / Tier 2 statically confirmed / Tier 3
  entailment-only). Never aggregated across tiers without the per-tier
  breakdown alongside.
- **T5 Migration** (optional) — behavioral-test pass rate; intended
  differences must fall exactly on detected drift lines.
- **T6 Versioned judgment** — the same code instance judged against two clause
  versions with different correct answers; metric is **paired accuracy** (both
  verdicts correct). Minimum **20 pairs** at M4 (T4.2). This is the metric
  that makes the temporal claim falsifiable.

### Abstention handling (binds T4.4)

An abstention ("insufficient evidence") is neither a TP nor an FP. T1–T3 are
reported at full coverage (abstention scored as a miss for recall) **and** as
coverage/accuracy pairs (metric on the answered subset + answer rate).
Headline numbers use the full-coverage figures; hiding a low answer rate
behind a high answered-subset F1 is not permitted.

### Statistical reporting

Headline comparisons carry **bootstrap 95% confidence intervals** and a
**paired significance test** (paired by instance). Stratified cells are small
(7 classes × 2 locus types); no headline claim without an interval.

---

## Part 4 — Targets (the bar, set at Schema Freeze)

Two pass/fail bars; everything else is reported without a bar (v1 has no
basis to set more, and unmet decorative targets read badly in review):

1. **T1 F1 ≥ 0.70 overall** on the frozen test split.
2. **Headline:** the agent beats dense-RAG on the **interprocedural stratum**
   by **≥ +10 F1 points**, with the 95% bootstrap CI on the difference
   excluding zero and paired-test p < 0.05.

Decision rules (not bars):

- **Oracle-slice deconfounder (at M4 go/no-go, T4.5):** if the agent does not
  beat the oracle-slice single-shot baseline on the interprocedural stratum,
  the contribution is reframed as the slicer, not the loop, **before**
  scaling. This comparison is mandatory at M4, not deferred to Phase 5.
- **T6:** a version-blind system scores ≤ ~50% paired accuracy by
  construction; ours must clearly exceed that. Proposed reporting bar for the
  paper: **paired accuracy ≥ 0.70** on ≥ 20 pairs — flagged as a proposal,
  A/B may object at sign-off.

---

## Part 5 — Sign-off

| Track | Scope of agreement | Status |
|---|---|---|
| A | Part 1 signatures + structured-return rule are what T1.6 ships | pending |
| B | Part 2 literals/strata match T2.2–T2.6 outputs; Part 3 scores them | pending |
| C | Owns Parts 3–4 implementation (T4.2); stub parity clause | author |

Sign-off = a confirming message in each track chat, then this line updates to
`accepted` with the date. Until then this document is `proposed` and T0.4 is
not done.
