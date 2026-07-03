# CLAUDE.md — COBOL Archaeologist

## What this repo is

A system + benchmark for detecting where legacy COBOL banking code has **drifted** from the
financial regulation it was built to satisfy (stale thresholds, missing checks, contradictions,
stale reference data, boundary errors, dead compliance code), with verified explanations and an
optional migration step. Drift detection is the research contribution; the benchmark is the moat.

Work is tracked by **task IDs** (T0.1…T7.5) defined in `docs/track-a-phase1-brief.md` (Track A
scope) and the master playbook (kept outside the repo). Always name the task ID you are
implementing in commits: `T1.1: <what changed>`.

## Current state

- **Done:** T0.5 AST decision (see `docs/T0.5-ast-decision-note.md`). Validated prototype:
  `src/cobol/spike_parser.py` — to be dissolved into the real package (see brief, T1.1).
- **Active:** Track A, Phase 1 (T1.1–T1.6) per `docs/track-a-phase1-brief.md`.

## Locked technical decisions — do not re-litigate

1. **AST backend:** tree-sitter with grammar `yutaro-sakamoto/tree-sitter-cobol`, **vendored**
   at `vendor/tree-sitter-cobol/` and **pinned to commit
   `e99dbdc3d800d5fa2796476efd60af91f6b43d93`**. Do not upgrade the grammar without re-running
   the T1.1 validation gate.
2. **Mandatory preprocessor** before any parse (line-count-preserving): mask
   `EXEC CICS/SQL/DLI … END-EXEC` (preserving a sentence-terminating period when `END-EXEC.`
   closed a sentence) and handle `COPY … REPLACING`. Lives in
   `src/cobol_archaeologist/ingest/cleaner.py`. Raw CardDemo CICS code is unparseable by every
   backend without this — it is not a workaround, it is a pipeline stage.
3. **GnuCOBOL `cobc` (3.1.2) is the compile/behavior oracle only** — never the parser. CICS
   programs will not compile under it; only batch `CB*` programs are runnable.
4. **All coordinates map to original source lines.** Any transformation (preprocess, copybook
   expansion) must carry a line-map back to the raw file. Benchmark labels are line-level;
   breaking this breaks the benchmark.
5. **Corpora:** AWS CardDemo (Apache 2.0, pin commit `59cc6c2fd7eb`) = anchor; IBM CICS CBSA
   (EPL 2.0) = secondary. Fetched by `scripts/fetch_corpora.sh` into `data/corpora/` —
   **never vendored into the repo**.

## Layout (target)

```text
src/cobol_archaeologist/
  ingest/cleaner.py            # preprocessor (T1.1 prereq)
  parser/paragraphs.py         # AST parse + paragraph spans (T1.1)
  parser/copybooks.py          # real copybook expansion + line-map (T1.1)
  static_analysis/call_graph.py  # PERFORM/GO TO + EXEC CICS LINK/XCTL edges (T1.2)
  static_analysis/dataflow.py    # interprocedural def-use (T1.3)
  static_analysis/slicer.py      # variable slicing (T1.4)
  model/run_cobol.py             # GnuCOBOL harness, sandboxed (T1.5)
  tools.py                       # agent tool layer facade (T1.6)
  schemas.py                     # pydantic models incl. DriftInstance
vendor/tree-sitter-cobol/        # pinned grammar
tests/                           # pytest; golden fixtures under tests/fixtures/
scripts/fetch_corpora.sh
docs/
```bash

## Conventions

- Python 3.12, `pydantic` for all inter-module data shapes, `pytest` for tests. Every tool in
  `tools.py` returns **structured data + source pointers, never raw code dumps**.
- Each T1.x task has an explicit "done when" gate in the brief — write the gate's test first.
- Keep a regex fallback path where the brief says so; consumers must never hard-block on the AST.
- `tree_sitter==0.21.3` pinned (grammar built via `Language.build_library`); changing bindings
  is a deliberate migration, not a drive-by upgrade.

## Commands

```bash
pip install -e ".[dev]"           # once packaging lands (T1.1 scaffolding)
bash scripts/fetch_corpora.sh     # clone pinned CardDemo/CBSA into data/corpora/
pytest tests/ -x -q               # gates must stay green
```
