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
| dev | 509 | 400 | 109 | 114 |
| test | 116 | 116 | 0 | 45 |

| split | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train | 54 | 32 | 26 | 2 | 67 | 23 | 103 |
| dev | 150 | 32 | 59 | 23 | 45 | 45 | 155 |
| test | 27 | 5 | 17 | 2 | 9 | 15 | 41 |

Test splits that have been inspected move into dev. The current test split
(E3, `docs/tasks/E3.md`) is 116 synthetic rows, 45 cross-program, built from
110 Claude-authored seed programs in `data/benchmark/seed/programs/e3/` that no
other split uses: refund-cutoff hosts (FUNCTION MIN, EVALUATE), over-limit
gates with an explicit-consent route, closure-penalty chains whose penalty
step CALLs a run-control module, and 18 local hosts. Every host implements
every leg of its clause and passed 231 behaviour checks before mutation;
Claude judged 117 candidates and rejected one. The E1/E2 test split (145 rows)
and temporal pairs (44 rows) are now in dev, with their flawed programs
corrected there.

**Temporal pairs** (`data/benchmark/temporal/`): 22 pairs, 44 rows, all new
programs (6 pairs cross-program). Each pair is one byte-identical program
judged against two versions of a KYC beneficial-owner clause with opposite
verdicts: the 2016 KYC Master Direction as consolidated 2018-07-12
(conformant side) and the RBI KYC Directions, 2025 (stale-threshold side).
Targets, verified in the pinned primary texts: company controlling ownership,
more than 25 → more than 10 percent (10 pairs); trust beneficiaries, 15% or
more → 10 percent or more (7 pairs); partnership, more than 15 → more than 10
percent (5 pairs). Every program implements every leg of its clause (79
behaviour checks).

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

- The fresh test bases are template-generated families (20 cutoff hosts, 20
  gate hosts, 20 two-program chains, and local hosts), so rows within a
  family share structure. They share no program, identifier set, or source
  text with train/dev, but they are less varied than CardDemo code.
- The test split has no real-curated rows; the 43 annotated rows stay in dev.
- A row's source bundle is the base program, its copybooks, and every file the
  row's edit touches. For a cross-program chain the second program is in the
  bundle only when the edit is there, so on the same host a D6 row carries two
  programs and a benign row carries one.
- Twice an inspection after a run found benchmark programs that omitted part
  of their clause (E1's temporal programs; E1/E2's interest chains). Both sets
  are corrected in dev. The E3 programs were checked leg by leg before any run.
- In E3 every cross-program test row is a drift case, and the drift is visible
  enough that the retrieval baseline finds most of it; the margin gate is
  therefore near its ceiling. Future splits need harder cross-program rows,
  including conformant ones.
- Every fresh temporal pair has the same direction (old side conformant, new
  side D1), and all come from beneficial-owner thresholds, the only numeric
  changes in the anchor regulations that could be verified in the pinned
  primary texts.
- The data is drift-heavy, so an all-drift predictor gets high F1 with
  balanced accuracy 0.5. Report balanced accuracy and answer rate with F1.
- Eight annotation candidates were excluded for insufficient primary evidence
  rather than forced to a label.
- The plausibility verdicts behind the existing train/dev rows
  (`judgements.jsonl`) were made by OpenAI models when the system under test
  was Claude. The detector is now `gpt-6-luna` (OpenAI), so the fresh test rows were
  judged by Claude (`claude-opus-5.5`); the existing verdicts are kept as the
  historical record. Claude also authored the fresh seed programs, so judge and
  author are not independent; the judge is independent of the system under
  test, which is what the integrity rule requires.

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
