# Datasheet — COBOL Archaeologist Benchmark

In the spirit of Gebru et al., "Datasheets for Datasets". Every number here is
computed from the files in `data/benchmark/` as they are now.

## Motivation

The benchmark measures whether a system can detect where legacy COBOL banking
code has drifted from the regulation it was built to satisfy — stale
thresholds, missing checks, contradictions, stale reference data, boundary
errors, and dead compliance code — with a verified, line-level explanation.
General code-QA and vulnerability benchmarks do not test whether a compliance
judgment is grounded in both the cited clause and the cited source lines.

## Composition

One row is one `DriftInstance` (`src/cobol_archaeologist/schemas.py`): a
regulation clause pinned to a version and effective date, one or more source
loci, one class (D1–D7), program/paragraph/line labels, and a gold rationale.

| split | rows | synthetic | real-curated | interprocedural |
| --- | --- | --- | --- | --- |
| train | 307 | 307 | 0 | 7 |
| dev | 298 | 255 | 43 | 36 |
| test | 0 | — | — | — |

| split | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train | 54 | 32 | 26 | 2 | 67 | 23 | 103 |
| dev | 90 | 22 | 38 | 18 | 35 | 23 | 72 |

The previous test split was evaluated repeatedly, so its rows were moved into
dev. A fresh test split is being built (`docs/tasks/B1.md`).

**Temporal pairs** (`data/benchmark/temporal/`): 20 pairs, 40 rows. Each pair
is byte-identical code judged against two versions of a regulation, with
opposite verdicts (one conformant side, one drift side).

## Collection

1. **Regulations.** RBI (Commercial Banks – Credit Cards and Debit Cards:
   Issuance and Conduct) Directions, 2025, the KYC clauses it incorporates,
   and the RBI KYC Directions, 2025; the repealed 2022 Master Direction
   supplies older clause versions. Clause records:
   `data/regulations/clauses.jsonl`; source PDFs pinned by SHA-256 in
   `data/regulations/sources/MANIFEST.json`.
2. **Synthetic rows.** Mutation operators (`benchmark/mutate.py`) apply MO-1
   to MO-6 drift edits, interprocedural MO-1×/MO-3×/MO-6× variants, and benign
   MO-0 edits to AWS CardDemo programs and repository-authored seed programs
   (`data/benchmark/seed/programs/`). Every mutation must compile and change
   behaviour as intended under GnuCOBOL 3.2.0, and passes a plausibility
   judge (`docs/judge-rubric.md`).
3. **Real-curated rows.** 43 hand-authored cases citing primary RBI text,
   annotated under `docs/annotation.md` (records in
   `data/benchmark/annotation/`).
4. **Splits.** `benchmark/splits.py` assigns whole base-program groups to
   splits, so no program appears in two splits; `benchmark/freeze.py` merges
   the annotated rows and writes `splits.manifest.json` with the SHA-256 of
   every split file.

## Preprocessing

All source passes through the line-count-preserving preprocessor
(`ingest/cleaner.py`) before parsing. Every locus and line label refers to
original source line numbers.

## Leakage controls

- Gold-only fields (gold rationale, provenance, mutation metadata) never reach
  a system; `DriftPrediction` cannot carry them.
- Benign MO-0 edits and style diversification mean edit artifacts alone do
  not predict drift. The surface probe (`data/benchmark/surface-probe.jsonl`)
  scores AUC 0.50.
- Base-program groups never cross splits.

## Known limitations

- Interprocedural rows and D6 rows are concentrated in dev; the fresh test
  split is required to cover them.
- The data is drift-heavy, so an all-drift predictor gets high F1 with
  balanced accuracy 0.5. Report balanced accuracy and answer rate with F1.
- Eight annotation candidates were excluded for insufficient primary evidence
  rather than forced to a label.

## Recommended metrics

Per-class F1 stratified by interprocedurality, balanced accuracy, answer rate,
temporal paired accuracy with an exact binomial interval, and the verification
tier of each finding. `eval/report.py` computes all of them.

## Licensing

- AWS CardDemo: Apache-2.0, pinned commit `59cc6c2fd7eb` (`data/manifest.json`).
- Repository-authored seed programs, annotation guidelines, and code: MIT.
- RBI regulation text keeps its original rights; it is quoted for research and
  citation.

## Maintenance

There is one copy of the benchmark. A correction regenerates the affected files
in place and updates `splits.manifest.json`; the previous state is in Git
history.
