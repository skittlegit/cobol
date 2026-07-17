# CONTRACT.md — Cross-track interface contract (T0.4)

**Version:** 1.3 · **Status:** ACCEPTED
Signed by all three tracks: 2026-07-07; amended 2026-07-12 and 2026-07-17
(CONTRACT CHANGEs; see the amendment log)
**Governs:** the tool I/O boundary (Track A implements, Track C consumes) and
the evaluation metrics + targets (Track C implements, Tracks A/B build toward).
Changes from here on are **CONTRACT CHANGEs** and must be flagged to all three
tracks before merge.

Binding order: this document > track briefs > CLAUDE.md, for the interfaces it
covers. The `DriftInstance` schema itself is frozen separately (T0.3,
`src/cobol_archaeologist/schemas.py`); this document binds against it.

---

## Part 1 — Tool I/O contract

**Normative source: `src/cobol_archaeologist/tool_types.py`** (Track A,
amendment A1). That file defines the pydantic return models and the `ToolLayer`
runtime-checkable Protocol; this section reproduces the Protocol for reference,
but on any divergence **the committed file wins** and the divergence is a
CONTRACT CHANGE to adjudicate.

```python
@runtime_checkable
class ToolLayer(Protocol):
    def read_paragraph(self, program: str, name: str) -> ParagraphView: ...
    def read_program(self, program: str) -> ProgramView: ...
    def find_callers(self, program: str, para: str) -> list[NodeRef]: ...
    def find_callees(self, program: str, para: str) -> list[NodeRef]: ...
    def trace_variable(
        self, var: str, program: str | None = None
    ) -> VariableTrace: ...
    def slice_on(self, var: str, program: str | None = None) -> Slice: ...
    def resolve_copybook(self, name: str) -> CopybookExpansion: ...
    def get_data_layout(self, record: str) -> DataLayout: ...
    def grep(self, pattern: str) -> GrepResult: ...
    def run_cobol(
        self, snippet: str, inputs: RunInputs | None = None
    ) -> RunResult: ...
    def search_regulations(self, query: str) -> list[RegSearchHit]: ...
```

Notes carried from sign-off: `trace_variable`/`slice_on` take an optional
`program` scope (amendment A2). `search_regulations` has a typed return
(`list[RegSearchHit]`); Track A's `tools.py` ships it raising
`NotImplementedError` — **Track C owns the implementation** (T3.1–T3.3).

### Structured-return rule (applies to every tool)

Every return is a **pydantic model** carrying **summaries + source pointers**
(program, paragraph, line spans) — never full-file dumps. Any code text is
capped at **~60 lines** with a pointer to fetch more. Every line number in a
public return refers to the **original source file** (via the preprocessor
LineMap), never to preprocessed text.

### Stub parity clause

`StubToolLayer` (Track C) implements the `ToolLayer` Protocol and returns
instances of the **same return models** from `tool_types.py`. Track C's test
suite must assert `isinstance(stub, ToolLayer)` (the Protocol is
runtime-checkable) so structural conformance is continuously enforced, not
discovered at the seam. The Week-7 seam test (stub → real) must be a one-line
constructor swap; any divergence discovered there is a contract bug, triaged
against `tool_types.py`.

---

## Part 2 — Schema bindings consumed by eval

From the T0.3 freeze — restated here because the metrics are defined over these
exact values:

- `drift_type` literals: `D1_stale_threshold`, `D2_missing_rule`,
  `D3_contradictory`, `D4_stale_reference_data`, `D5_boundary_error`,
  `D6_dead_code`, `D7_conformant`.
- Stratification keys: `code_locus.is_interprocedural` (bool) and `drift_type`.
  Every metric below is reported overall **and** per stratum.
- Temporal fields: `regulation_clause.version` + `effective_date` are required;
  T6 pairs are keyed on same `code_locus`, different (`version`,
  `effective_date`).
- **`code_locus` shape (v2, 2026-07-12 CONTRACT CHANGE):** the flat
  `programs` / `paragraphs` / `line_span` fields are **replaced** by
  `loci: list[SourceLocus]`, each a `(program, paragraph?, file?, line_span)`
  binding a line span to exactly one program (and optionally a copybook `file`).
  `slice_vars` and the required `is_interprocedural` bool remain. This is what
  makes interprocedural localization — the headline metric — expressible: a line
  now resolves to a specific program. The `is_interprocedural` validator is
  **one-way** (>1 distinct program ⇒ `True`; the reverse is not forced, since a
  single-program cross-paragraph locus may also be interprocedural).
- **T6 pairing convention (Track B sign-off note 1) — preserved:** there is no
  `pair_id` field; pairing rests on **struct equality of `code_locus`**, now
  over `loci`. The reshape from flat fields to `loci` is **not** a loosening: the
  T2.5 generator still **guarantees byte-identical `code_locus`** (hence
  byte-identical `loci`) between a pair's two instances. Adding `pair_id`
  remains a deliberately deferred post-freeze CONTRACT CHANGE.
- **`current_value` (v2):** `CurrentValue` is recursive and typed —
  `kind == "composite"` nests `dict[str, CurrentValue]`; every node carries an
  optional typed `comparator` (`strictly_greater`/`at_least`/`strictly_less`/
  `at_most`/`equal`/`not_equal`) and `note`; composites carry no comparator.
- **`target_path` (v2):** dotted path into `regulation_clause.current_value`,
  **required** for D1/D5 against a composite clause (resolving to a leaf), `None`
  otherwise. `resolve_path(current_value, path)` in `schemas.py` is the single
  canonical accessor for B's emitters and C's metrics.
- System findings are emitted `DriftInstance`-shaped (T3.6) so predictions and
  gold share one schema.

---

## Part 3 — Metrics (definitions of record)

- **T1 Detection** — does this locus conform? Precision / Recall / F1 on a
  class-balanced set (drift = positive; D7 = negative).
- **T2 Localization** — Accuracy@k for k ∈ {1, 3} at program, paragraph, and
  line granularity, plus line-level overlap (predicted lines vs
  `labels.line_level`). **D2 convention (Track B sign-off note 2):** for
  missing-rule instances the offending lines do not exist, so
  `labels.line_level` holds the **insertion-point line(s)** where the check
  should live; D2 line-localization is insertion-point matching, not
  deleted-code matching. The convention is unchanged under v2; note only that
  `line_level` entries are now `SourceLineRef`s — `(program, file, line)` — so
  interprocedural line-overlap scoring is well-defined (each label line resolves
  to a specific program/file). Full per-class conventions land in `ANNOTATION.md`
  (T5.1).
- **T3 Classification** — Macro-F1 over all seven classes D1–D7.
- **T4 Faithfulness** — fraction of findings where BOTH the cited clause is
  correct AND the cited code fact matches `gold_rationale`. **Reported per
  verification tier** (Tier 1 executed / Tier 2 statically confirmed / Tier 3
  entailment-only). Never aggregated across tiers without the per-tier breakdown
  alongside.
- **T5 Migration** (optional) — behavioral-test pass rate; intended differences
  must fall exactly on detected drift lines.
- **T6 Versioned judgment** — the same code instance judged against two clause
  versions with different correct answers; metric is **paired accuracy** (both
  verdicts correct). Minimum **20 pairs** at M4 (T4.2). This is the metric that
  makes the temporal claim falsifiable.

### Abstention handling (binds T4.4)

An abstention ("insufficient evidence") is neither a TP nor an FP. T1–T3 are
reported at full coverage (abstention scored as a miss for recall) **and** as
coverage/accuracy pairs (metric on the answered subset + answer rate). Headline
numbers use the full-coverage figures; hiding a low answer rate behind a high
answered-subset F1 is not permitted.

### Statistical reporting

Headline comparisons carry **bootstrap 95% confidence intervals** and a **paired
significance test** (paired by instance). Stratified cells are small (7 classes
× 2 locus types); no headline claim without an interval.

### Surface-leakage standard (Gate E; v1.3)

Gate E is split by the information available to the attacker:

1. **Artifact-only attacker.** This attacker sees only the shipped evaluation
   artifact. Of the registered surface features, only `literal_roundness` is
   computable without a seed base. It remains a **hard build gate at chance**:
   the deterministic one-feature probe passes only when its bootstrap 95% AUC
   confidence interval includes 0.5. The build manifest records the feature,
   AUC, interval, pass/fail result, and this definition together.
2. **Attacker with bases.** This attacker may diff against the published seed
   bases or memorized source. The aggregate registered surface probe is
   **reported with its bootstrap AUC interval, not gated at chance**. It is the
   mandatory seventh baseline in T5.3. Before headline runs, T5.3 must declare
   the margin by which a system must beat this baseline; the results report the
   paired delta and bootstrap 95% CI, and a headline system clears the floor
   only when the declared margin is met and the interval excludes zero.

This split is normative: the artifact-only gate cannot be replaced by the
aggregate, and the aggregate attacker-with-bases result cannot be omitted or
turned into a methodology footnote.

---

## Part 4 — Targets (the bar, set at Schema Freeze)

Two pass/fail bars; everything else is reported without a bar (v1 has no basis
to set more, and unmet decorative targets read badly in review):

1. **T1 F1 ≥ 0.70 overall** on the frozen test split.
2. **Headline:** the agent beats dense-RAG on the **interprocedural stratum** by
   **≥ +10 F1 points**, with the 95% bootstrap CI on the difference excluding
   zero and paired-test p < 0.05.

Decision rules (not bars):

- **Oracle-slice deconfounder (at M4 go/no-go, T4.5):** if the agent does not
  beat the oracle-slice single-shot baseline on the interprocedural stratum, the
  contribution is reframed as the slicer, not the loop, **before** scaling. This
  comparison is mandatory at M4, not deferred to Phase 5.
- **T6 (restated per Track B sign-off note 3):** paired accuracy ≥ 0.70 on ≥ 20
  pairs stands as the **M4 reporting bar only** — at n=20 its 95% CI (~[0.48,
  0.86]) does not exclude the 0.5 version-blind floor, so it is not a paper
  claim. The **paper claim** is: paired accuracy exceeds the 0.5 floor with the
  **exact binomial CI reported**, on a pair count scaled with T2.5's growth to
  50–150 real instances at M5.

---

## Part 5 — Sign-off

- **Track A:** Part 1 is normative via `tool_types.py`; amendments A1 and A2
  are folded in. Status: **accepted 2026-07-07**.
- **Track B:** Part 2 literals/strata match T2.2–T2.6; Part 3 scores them; notes
  1–3 are recorded; v1.3 Gate E split signed. Status: **accepted 2026-07-07;
  v1.3 accepted 2026-07-17**.
- **Track C:** Owns Parts 3–4 implementation (T4.2), the stub parity clause, and
  document ownership. Status: **author / accepted 2026-07-07; v1.3 ratified
  2026-07-17**.

---

## Amendment log

- **v1.0 → v1.1 (2026-07-07, sign-off round — pre-acceptance, not CONTRACT
  CHANGEs):** A1 — Part 1 bound to `tool_types.py` (return models +
  runtime-checkable `ToolLayer` Protocol); prose signature list replaced by the
  Protocol; `isinstance(stub, ToolLayer)` added to the stub parity clause.
  A2 — `trace_variable`/`slice_on` gained `program: str | None = None`;
  `run_cobol` inputs typed `RunInputs | None`; `search_regulations` returns
  `list[RegSearchHit]`. B1 — T6 pairing convention recorded in Part 2
  (byte-identical `code_locus`, T2.5 obligation; `pair_id` deferred). B2 — D2
  insertion-point line-label convention added to Part 3 T2. B3 — T6 bar split:
  0.70/20 as M4 reporting bar; paper claim = exceeds 0.5 floor with exact
  binomial CI, pairs scaled at M5.
- **v1.1 → v1.2 (2026-07-12, CONTRACT CHANGE, ratified by C, blast radius B):**
  amends the `schemas.py` freeze to v2. See
  `docs/reviews/2026-07-12/contract-change-track-c-RESOLVED.md`.
  Item 1 (F2) — flat `code_locus` replaced by `loci: list[SourceLocus]` +
  `SourceLineRef` line labels, so interprocedural localization is expressible;
  one-way `is_interprocedural` validator. Item 2 (F1c) — `CurrentValue` is
  recursive/typed with a per-node `comparator` field (Option C, not the rejected
  top-level hoist). Item 3 (F-C1) — `DriftInstance.target_path` disambiguates
  which leaf of a composite clause drifted (required for composite D1/D5).
  Track A: no action (consumes DriftInstances, `tool_types.py` untouched).
- **v1.2 → v1.3 (2026-07-17, CONTRACT CHANGE, ratified by C, signed by B,
  blast radius B/C; A FYI):** splits Gate E by attacker information. The
  artifact-only `literal_roundness` probe remains a hard at-chance build gate
  (bootstrap 95% AUC CI includes 0.5). The aggregate attacker-with-bases probe
  becomes a reported floor and mandatory seventh T5.3 baseline; headline runs
  must beat it by a predeclared margin with paired bootstrap CIs. Resolution:
  `docs/reviews/2026-07-17/contract-change-gate-e-RESOLVED.md`.
