# COBOL Archaeologist

Detecting where legacy COBOL banking code has **drifted** from the financial
regulation it was built to satisfy — with verified, line-level explanations and
an optional migration step.

Decades-old banking systems encode compliance logic that has quietly rotted:
thresholds that regulation has since changed, checks that were never added,
contradictory branches, stale reference data, off-by-one boundary conditions,
and dead code that _looks_ like compliance. This project builds (1) a
program-analysis toolchain that lets an agent investigate real COBOL the way an
archaeologist would, and (2) a labeled benchmark of drift instances to measure
it. **Drift detection is the research contribution; the benchmark is the moat.**

## How it works

```text
raw COBOL (CardDemo / CBSA)
  -> ingest/cleaner.py
     line-count-preserving preprocessor
  -> parser/
     tree-sitter AST, typed paragraphs, copybooks, LineMap
  -> static_analysis/
     call graph, interprocedural def-use, variable slicing
  -> tools.py
     agent facade with structured data and source pointers
  -> drift detection and labeled benchmark instances
```

Two invariants hold everywhere:

- **Line-number fidelity is sacred.** Every transformation (preprocessing,
  copybook expansion) carries a line-map back to the raw file; benchmark labels
  are line-level.
- **GnuCOBOL `cobc` is the compile/behavior oracle only, never the parser.**
  CICS programs do not compile under it by design; only batch `CB*` programs are
  runnable.

## Status

- **M0 — spike & decisions:** parser bake-off and AST decision. Done.
- **M1 — slicing validated:** Phase 1, T1.0-T1.6: preprocessor, parser, call
  graph, dataflow, slicer, run harness, and tool layer. Active.
- **M2+:** mutation-based benchmark generation, drift detectors, regulation
  search, and migration. Planned.

The validated prototype lives at
[`src/cobol/spike_parser.py`](src/cobol/spike_parser.py) (preprocess → parse →
paragraph extraction; exact on 26/26, 6/6, and 85/85 paragraphs across the three
spike programs, including a 4,236-line CICS program). It is reference logic
being dissolved into the real package during T1.1, then deleted.

## Getting started

> Packaging lands with T1.0 scaffolding; until then only the spike is runnable.

```bash
pip install -e ".[dev]"
bash scripts/fetch_corpora.sh
pytest tests/ -x -q
```

The package targets Python 3.12 with `tree_sitter==0.21.3`, `pydantic>=2`,
`pytest`, and `ruff`. `fetch_corpora.sh` shallow-clones pinned CardDemo and CBSA
copies into `data/corpora/`.

The tree-sitter COBOL grammar (`yutaro-sakamoto/tree-sitter-cobol`) is vendored
at `vendor/tree-sitter-cobol/` and pinned by commit; corpora are fetched,
**never vendored**.

## Repository layout

```text
src/cobol_archaeologist/
  ingest/cleaner.py              # mandatory preprocessor
  parser/paragraphs.py           # AST parse + paragraph spans
  parser/copybooks.py            # copybook expansion + LineMap
  static_analysis/call_graph.py  # PERFORM/GO TO + EXEC CICS LINK/XCTL edges
  static_analysis/dataflow.py    # interprocedural def-use
  static_analysis/slicer.py      # variable slicing
  model/run_cobol.py             # sandboxed GnuCOBOL harness (oracle)
  tools.py                       # agent tool layer facade
  schemas.py                     # pydantic models incl. DriftInstance
vendor/tree-sitter-cobol/        # pinned grammar
tests/                           # pytest; golden fixtures under tests/fixtures/
scripts/fetch_corpora.sh         # pinned corpus fetch (data/ is gitignored)
docs/                            # task briefs and decision notes
```

## Corpora

- **AWS CardDemo:** anchor corpus, Apache 2.0.
- **IBM CICS CBSA:** secondary corpus, EPL 2.0.

Both are pinned to specific commits by `scripts/fetch_corpora.sh` and live
outside version control under `data/corpora/`.

## Development

Work is tracked by task IDs (T0.1…T7.5); commits are prefixed with the task
being implemented (`T1.1: <what changed>`). Each task has an explicit "done
when" gate in [the Phase 1 brief](docs/track-a-brief.md), written as a test
_before_ implementation. Locked technical decisions (grammar pin, preprocessor
contract, oracle boundary, line-map invariant) are recorded in
[`CLAUDE.md`](CLAUDE.md) — read it before contributing.
