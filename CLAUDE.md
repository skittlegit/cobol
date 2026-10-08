# CLAUDE.md — COBOL Archaeologist

## What this repo is

A system and benchmark for detecting where legacy COBOL banking code has
**drifted** from the regulation it was built to satisfy: stale thresholds,
missing checks, contradictions, stale reference data, boundary errors, and dead
compliance code (classes D1–D6; D7 is conformant). The detector investigates
code with program-analysis tools and must verify every finding before it
counts. An optional migration step patches verified findings.

## Where things are

| Path | What it is |
| --- | --- |
| `STATUS.md` | The plan: every task, its state, and the current result. Source of truth for project state. |
| `docs/tasks/<ID>.md` | One file per task: goal, approach, done-when, result. |
| `docs/architecture.md` | How the pieces fit, the data shapes, and the evaluation gates. |
| `docs/annotation.md` | The protocol under which the existing 43 real-curated rows were annotated. |
| `docs/judge-rubric.md` | The plausibility rubric for judging benchmark rows. |
| `data/manifest.json` | Pinned corpora and anchor regulations. |
| `data/benchmark/` | `train/dev/test.jsonl`, `temporal/`, seed programs, build inputs. |
| `data/eval/<split>/` | Current results: `<system>.jsonl` and `report.json`/`report.md`. |

Source layout (`src/cobol_archaeologist/`):

- `ingest/cleaner.py` — mandatory preprocessor; `parser/` — tree-sitter AST,
  paragraphs, copybooks, line maps; `static_analysis/` — call graph, dataflow,
  slicer; `tools.py` — the tool layer the detector calls.
- `model/verify.py` — tiered verifier; `model/run_cobol.py` — GnuCOBOL harness;
  `model/prompt.py` — class policy text and response shapes.
- `agent/` — D1–D7 evidence guards (`policy.py`, `hunts/`), trajectories,
  offline stub tools.
- `eval/` — `codex.py` (the only way models are called), `bridge.py` (tool
  bridge inside a task), `detector.py`, `baselines.py` (rag_reranker),
  `runner.py`, `report.py`, `metrics.py`.
- `benchmark/` — mutation, build, judging, splits, freeze.
- `rag/` — clause chunking, index, retrieval. `migration/` — `case.py`,
  `patch.py`, `validate.py` (GnuCOBOL fixtures), `run.py` (generate, validate,
  report); one directory per case under `data/migration/`. `mcp_server/` — the
  tools over MCP stdio.

## Working rules

1. **One version of everything.** No `v1/`, `v2/`, `legacy/`, `-old`, `-rerun`,
   or `sample` copies of code, data, or results. Regenerating something
   overwrites it in place. Git history is the archive (the last commit before
   consolidation is e5595ede).
2. **One way to do each thing.** Models are called only through
   `eval/codex.py`. Results are written only by `eval/runner.py` and scored
   only by `eval/report.py`. Do not add parallel runners or alternative paths.
3. **Branch:** work on `master` or a short-lived feature branch; merge back.
   Commit subjects start with the task ID, e.g. `D4: check reachability for D6`.
4. **Update `STATUS.md` in the same commit** as the work that changes a task's
   state. Record the outcome in that task's `docs/tasks/<ID>.md`.
5. **Tests first** for new behaviour; `pytest tests/ -q` and `ruff check .`
   must pass before a commit.
6. **No ceremony.** No receipts, seals, sidecar `.sha256` files, flags files,
   or per-attempt evidence directories. A result file plus its report is the
   evidence.

## Evaluation integrity (non-negotiable)

- The gates are fixed in `eval/report.py` (`GATES`). They may change only
  before a test run, never after looking at test results.
- Tune only on `train`/`dev`. The `test` split and `temporal` pairs are run
  once per frozen detector version, for the official decision.
- The detector never sees gold labels, mutation provenance, or gold
  rationales. Everything shown to a model is detector-visible only.
- Every emitted finding must pass the verifier and the class guard. A rejected
  finding becomes an abstention; never relax a check to raise a score.
- Judges and verifiers must be a different model family from the system under
  test. Benchmark mutation must include benign MO-0 edits and style
  diversification.

## Locked technical decisions

1. **AST backend:** tree-sitter grammar `yutaro-sakamoto/tree-sitter-cobol`,
   vendored at `vendor/tree-sitter-cobol/`, pinned to
   `e99dbdc3d800d5fa2796476efd60af91f6b43d93`; bindings `tree_sitter==0.21.3`.
2. **Preprocessor before every parse** (line-count preserving): mask
   `EXEC CICS/SQL/DLI … END-EXEC` and handle `COPY … REPLACING`.
3. **GnuCOBOL `cobc` is the compile/behaviour oracle only, never the parser.**
   3.2.0 is the version of record (`>=3.1.2,<4` supported). Only batch `CB*`
   programs compile; CICS programs failing is expected. Gate numbers come from
   the real toolchain, never from a simulation of it.
4. **Line-number fidelity:** every line reported refers to the original source
   file; every transformation carries a line map.
5. **Corpora:** AWS CardDemo (Apache-2.0, pin `59cc6c2fd7eb`) is the anchor;
   IBM CICS CBSA (EPL-2.0) is secondary. Fetched by `scripts/fetch_corpora.sh`
   into `data/corpora/`, never vendored. Pins live in `data/manifest.json`.
6. **Anchor regulations:** RBI (Commercial Banks – Credit Cards and Debit
   Cards: Issuance and Conduct) Directions, 2025 (effective 2025-11-28) plus
   the KYC/AML clauses its paragraph 90 incorporates, and the RBI KYC
   Directions, 2025. The repealed 2022 Master Direction supplies older
   versions for temporal pairs. Clause records: `data/regulations/clauses.jsonl`.
7. **Verification tiers:** 1 executed, 2 static, 3 entailment-only; the tier
   is recorded per finding and tier-3-only findings are not emitted.

## Who does what

- **Luna (`gpt-6-luna`, the cheap model):** bulk model work only — detector
  runs, the rag_reranker baseline, and migration patch generation. Always
  called through `eval/codex.py` (Codex in WSL with the ChatGPT login;
  `COBOL_ARCH_MODEL` / `COBOL_ARCH_EFFORT` override for dev runs). Model and
  effort are part of every `run_key`.
- **Claude (the agent maintaining this repo):** everything else — code, new
  benchmark programs, plausibility judging (`benchmark-packets` →
  `judgements` → `benchmark-apply`), temporal-pair review, error analysis,
  and tuning. Claude is a different family from the detector, as the
  integrity rule requires. No human annotation passes are required.
- **Entailment verifier:** DeBERTa NLI (`model/verify.py`), a third family.

Run model and compiler work inside WSL: `wsl -d Ubuntu -- bash
scripts/wsl_run.sh <module> ...` (native Windows GnuCOBOL can hang).

## Commands

```bash
pip install -e ".[dev,models]"
bash scripts/fetch_corpora.sh
pytest tests/ -q && ruff check .

python -m cobol_archaeologist.eval.runner detector --split dev [--ids ...]
python -m cobol_archaeologist.eval.runner rag_reranker --split test
python -m cobol_archaeologist.eval.report --split test
python -m cobol_archaeologist.migration.run validate   # or: generate, report
cobol-archaeologist benchmark-packets --input ROWS --out PACKETS.md
cobol-archaeologist benchmark-apply --input ROWS --judgements J --accepted-out A --rejected-out R
```
