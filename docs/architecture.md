# Architecture

## Pipeline

```text
COBOL source (CardDemo, seed programs)
  -> ingest/cleaner.py        line-preserving preprocessing (EXEC masking, COPY REPLACING)
  -> parser/                  tree-sitter AST, paragraphs, copybooks, LineMap
  -> static_analysis/         call graph, interprocedural def-use, slicing
  -> tools.py                 ToolLayer: bounded, source-pointed tool results
  -> eval/bridge.py           the ToolLayer as a command inside a Codex task
  -> eval/detector.py         one adaptive investigation per case + host checks
  -> model/verify.py          tier 1 executed / tier 2 static / tier 3 entailment
  -> eval/runner.py           data/eval/<split>/<system>.jsonl
  -> eval/report.py           gates and the GO / NO_GO / NOT_EVALUABLE decision
```

## Data shapes (`schemas.py`)

- `RegulationClause` — document, clause id, version, effective date, text,
  and an optional typed `current_value` (scalar or composite).
- `DriftInstance` — a gold benchmark row: clause, `code_locus` (loci with
  program/paragraph/file/line span, slice variables, interprocedural flag),
  `drift_type` (D1–D7), labels (program/paragraph/line), gold rationale, and
  provenance (synthetic mutation or real-curated).
- `DriftPrediction` — what a detector may emit: the same semantic fields but no
  provenance and no gold rationale.
- `EvaluationRecord` (`eval/schemas.py`) — one gold row paired with one
  system's output, trajectory, verification, and `run_key`.

`schemas.py` is the interface between benchmark, detector, and evaluation;
change it only together with every consumer and its tests.

## The detector

One Codex task per case. The task directory holds only the materialized source
(mutation applied, no labels) and a descriptor with the detector-visible clause.
The model:

1. calls tools through `python -m cobol_archaeologist.eval.bridge ALIAS TOOL
   --arguments JSON` (at most 24 calls);
2. keeps an evidence ledger citing tool calls by sequence number;
3. checks its draft answer with `check_finding` (at most 6 checks) — the same
   ledger, class guard, and verifier the host applies, reporting the exact
   rejection so the model can fix it;
4. submits one finding or an abstention.

The host then rebuilds the tool log from the Codex event stream (never from
files the model can write), computes every observation hash itself, binds the
trusted clause and instance id, and re-runs the ledger check, the class guard,
and the verifier. Any failure is an abstention. Any command other than the
bridge, any file change, or any web/MCP call invalidates the task.

## The baseline

`rag_reranker`: hybrid retrieval with a cross-encoder reranker over the clause
index, plus a bounded query-relevant window of the program, in one model call
with no tools. Its findings pass the same verifier.

## Evaluation and decision (`eval/report.py`)

Required inputs: `data/eval/test/detector.jsonl`,
`data/eval/test/rag_reranker.jsonl`, `data/eval/temporal/detector.jsonl`.

| Gate | Threshold |
| --- | --- |
| T1 F1 (detector) | >= 0.70 |
| Balanced accuracy (abstention counts as a miss) | >= 0.65 |
| Answer rate | >= 0.60 |
| Answered accuracy | >= 0.80 |
| Interprocedural F1 advantage over rag_reranker | >= +0.10, bootstrap 95% CI above 0, paired randomization p < 0.05 |
| Temporal paired accuracy | >= 0.70 on >= 20 pairs |
| Unverified findings | 0 |

Decision: `NOT_EVALUABLE` if any required row is missing or failed on
infrastructure; `GO` if every gate passes; `NO_GO` otherwise. Statistics use
10,000 bootstrap resamples, 20,000 randomization samples, seed 20260823.

## Results files

Each `data/eval/<split>/<system>.jsonl` holds one record per row. Every record
carries a `run_key` derived from the system, prompt version, model, effort,
runtime source hash, row, and source hash. Running the runner again keeps rows
whose key matches and re-runs the rest, so a new detector version replaces the
old results in place.

## Benchmark

`benchmark/mutate.py` applies mutation operators (including benign MO-0 edits
and style diversification) to seed programs; `build.py` compiles and records
instances; `judge.py` writes review packets, loads the judge's verdicts (Claude,
never the detector's family), and keeps the plausible rows; `splits.py`
assigns base-program groups to train/dev/test without leakage; `freeze.py`
merges the human-annotated real-curated rows and writes the final splits and
`splits.manifest.json`. Temporal pairs (`data/benchmark/temporal/`) share
identical code under two regulation versions with opposite verdicts.

## Migration

`data/migration/<case_id>/` holds `case.json` (finding, edit scope, behaviour
fixtures, source assertions), `sources/`, `patch.diff`, `patch.json`, and
`validation.json`. `migration/run.py generate` asks Luna for a unified diff;
`validate` applies it, checks the edit scope, compiles every host program,
checks assertions, confirms the `intended` fixtures fail on the original code,
and runs every fixture on the patched code. A case's `finding_source` says
whether its finding is benchmark gold (`oracle`, an upper bound) or a verified
detector finding (`detector`).
