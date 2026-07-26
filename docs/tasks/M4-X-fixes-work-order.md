# Work Order — M4 config-2 fixes (X1, X1b, X2, X3′, X4)

**Owner:** Track C · **Type:** [code] · **Effort:** M
**Authority:** `docs/tasks/T4.5-decision.md` §8 (amended 2026-07-26, pre-run).
Read it and `docs/tasks/M4-f1-f2-triage.md` (including its Correction section)
before starting.

**Do not run any paid evaluation in this task.** Implementation and offline
tests only. Config 2 is authorized separately, after `--smoke 5`.

## Files

- `src/cobol_archaeologist/agent/hunts/d1.py`, `d3.py`, `d4.py`
- `src/cobol_archaeologist/agent/policy.py`
- `src/cobol_archaeologist/model/prompt.py`
- `tests/test_policy_hunts.py` (extend)

Do not modify `schemas.py`, `tool_types.py`, `tools.py`, `verify.py`, or
anything under `parser/`, `static_analysis/`, `ingest/`, `rag/`, `eval/`.

## X1 — `SourceLocus.file` semantics

(a) In the prediction prompt/schema description: `file` is **null** unless the
line resolves through a COPY expansion; it is **never** the program filename.
Give one positive and one negative example.
(b) Normalizer in `policy.py`: when a proposed locus has
`file == locus.program` (or `file` matches the program's own source filename),
set `file = None` before validation. Log the normalization on the trajectory
so it is measurable rather than silent.

**Gate:** a proposed prediction with `file="CLOSPEN1.cbl"` on program
`CLOSPEN1.cbl` normalizes to `file=None`, does **not** trigger the
`resolve_copybook` requirement, and validates. Build the fixture from a real
rejected row in `data/eval/m4/agent.jsonl`.

## X1b — D4 conditional copybook

`hunts/d4.py` currently calls `require_tools(transcript, {"resolve_copybook"})`
unconditionally. Condition it on `any(locus.file for locus in loci)`, matching
D1. **Gate:** a D4 prediction with no copybook locus validates without a
`resolve_copybook` call.

## X2 — class-derived evidence minimum

Replace the fixed 3-observation minimum with a per-class value: a
single-locus D1/D5 needs one literal observation; multi-locus D3 needs one per
locus; D2 (absence) keeps a higher floor since absence needs breadth. Declare
the table in `policy.py` with a comment citing this work order.
**Gate:** a single-locus D1 with one literal observation validates; a D2 with
one observation still fails.

## X3′ — code-fact binding, NOT a threshold change

**Do not modify the entailment threshold.** Require every emitted finding to
carry ≥1 code-fact observation bound to its claimed locus (same program, and
the line within the observed span). Findings satisfying this verify at Tier 2;
findings without it abstain. Record the NLI probability on every finding.
**Gates:** (a) a finding whose only support is entailment abstains;
(b) the same finding plus one bound code-fact observation emits at Tier 2;
(c) the entailment threshold constant is unchanged from config 1.

## X4 — composite-clause leaf disambiguation

When `clause.current_value.kind == "composite"`, surface the enumerated leaf
paths and their values to the hunt so the agent selects a `target_path`
explicitly rather than inferring from a bare literal. Evidence for the need:
*"the observed literal 500 is a penalty multiplier, not a resolved source
value for the no-capitalization leaf."*
**Gate:** on a composite-clause D1 fixture the hunt enumerates candidate leaves
and emits a resolving `target_path`.

## Regression gates (must stay green)

All existing `tests/test_policy_hunts.py`, `test_verify.py`,
`test_agent_loop.py`, and `test_search_regulations.py` gates. Verified emission,
D6 delegation, anti-shortcut policy, and the real/stub seam are unchanged.

## STATUS line

- **M4-X** | ready-for-review | C | `agent/hunts/{d1,d3,d4}.py`,
  `agent/policy.py`, `model/prompt.py` + tests. X1/X1b/X2/X3′/X4 per
  `T4.5-decision.md` §8. Offline only; config 2 not yet run.
