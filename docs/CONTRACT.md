# CONTRACT.md — Cross-track interface contract (T0.4)

**Version:** 1.1 · **Status:** ACCEPTED — signed by all three tracks 2026-07-07
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
amendment A1). That file defines the pydantic return models and the
`ToolLayer` runtime-checkable Protocol; this section reproduces the Protocol
for reference, but on any divergence **the committed file wins** and the
divergence is a CONTRACT CHANGE to adjudicate.

```python
@runtime_checkable
class ToolLayer(Protocol):
    def read_paragraph(self, program: str, name: str) -> ParagraphView: ...
    def read_program(self, program: str) -> ProgramView: ...
    def find_callers(self, program: str, para: str) -> list[NodeRef]: ...
    def find_callees(self, program: str, para: str) -> list[NodeRef]: ...
    def trace_variable(self, var: str, program: str | None = None) -> VariableTrace: ...
    def slice_on(self, var: str, program: str | None = None) -> Slice: ...
    def resolve_copybook(self, name: str) -> CopybookExpansion: ...
    def get_data_layout(self, record: str) -> DataLayout: ...
    def grep(self, pattern: str) -> GrepResult: ...
    def run_cobol(self, snippet: str, inputs: RunInputs | None = None) -> RunResult: ...
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
- **T6 pairing convention (Track B sign-off note 1):** there is no `pair_id`
  field; pairing rests on struct equality of `code_locus`. The T2.5 generator
  therefore **guarantees byte-identical `code_locus`** between a pair's two
  instances. Adding `pair_id` is a recognized cleaner design but is a
  post-freeze CONTRACT CHANGE, deliberately deferred.
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
  deleted-code matching. Full per-class conventions land in `ANNOTATION.md`
  (T5.1).
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
- **T6 (restated per Track B sign-off note 3):** paired accuracy ≥ 0.70 on
  ≥ 20 pairs stands as the **M4 reporting bar only** — at n=20 its 95% CI
  (~[0.48, 0.86]) does not exclude the 0.5 version-blind floor, so it is not
  a paper claim. The **paper claim** is: paired accuracy exceeds the 0.5
  floor with the **exact binomial CI reported**, on a pair count scaled with
  T2.5's growth to 50–150 real instances at M5.

---

## Part 5 — Sign-off

| Track | Scope of agreement | Status |
|---|---|---|
| A | Part 1 normative via `tool_types.py`; amendments A1 + A2 folded in | **accepted 2026-07-07** |
| B | Part 2 literals/strata match T2.2–T2.6; Part 3 scores them; notes 1–3 recorded | **accepted 2026-07-07** |
| C | Owns Parts 3–4 implementation (T4.2); stub parity clause; document owner | **author / accepted 2026-07-07** |

---

## Amendment log

- **v1.0 → v1.1 (2026-07-07, sign-off round — pre-acceptance, not CONTRACT
  CHANGEs):**
  A1 — Part 1 bound to `tool_types.py` (return models + runtime-checkable
  `ToolLayer` Protocol); prose signature list replaced by the Protocol;
  `isinstance(stub, ToolLayer)` added to the stub parity clause.
  A2 — `trace_variable`/`slice_on` gained `program: str | None = None`;
  `run_cobol` inputs typed `RunInputs | None`; `search_regulations` returns
  `list[RegSearchHit]`.
  B1 — T6 pairing convention recorded in Part 2 (byte-identical `code_locus`,
  T2.5 obligation; `pair_id` deferred).
  B2 — D2 insertion-point line-label convention added to Part 3 T2.
  B3 — T6 bar split: 0.70/20 as M4 reporting bar; paper claim = exceeds 0.5
  floor with exact binomial CI, pairs scaled at M5.
