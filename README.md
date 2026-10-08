# COBOL Archaeologist

Detecting where legacy COBOL banking code has **drifted** from the financial
regulation it was built to satisfy — with verified, line-level findings and an
optional migration step.

Decades-old banking systems encode compliance logic that quietly rots:
thresholds the regulator has since changed, checks that were never added,
contradictory branches, stale reference data, off-by-one boundaries, and dead
code that only looks like compliance. This project provides:

1. a program-analysis toolchain that lets an agent investigate real COBOL
   (preprocessing, parsing, call graphs, dataflow, slicing, a GnuCOBOL
   execution oracle);
2. a labeled benchmark of drift instances (D1–D7) anchored to RBI credit/debit
   card and KYC directions; and
3. a detector that investigates each case with those tools and must verify
   every finding before it counts.

## Status

See [STATUS.md](STATUS.md) and the project site at
https://skittlegit.github.io/cobol/. The current official evaluation (E2) is a
**GO** on a fresh 95-row held-out split:

| Measure | Result |
| --- | --- |
| Class F1 | 0.927 |
| Balanced accuracy | 0.909 |
| Temporal pairs right on both sides | 20/22 |
| Cross-program F1 margin over a retrieval-reranking baseline | +0.190 |
| Unverified findings | 0 |

E2 follows the first-look evaluation (E1, NO_GO), and its fixes were made
after inspecting E1's failures, so it is reported as post hoc.

## How it works

```text
COBOL source -> preprocessor -> tree-sitter parser -> call graph / dataflow / slicer
            -> tool layer -> detector (Codex task + tool bridge + self-check)
            -> verifier (executed / static / entailment) -> results -> gates
```

Details: [docs/architecture.md](docs/architecture.md).

## Getting started

```bash
pip install -e ".[dev,models]"
bash scripts/fetch_corpora.sh
pytest tests/ -q
python -m cobol_archaeologist.eval.report --split test
```

Running the detector needs WSL with the Codex CLI logged in through ChatGPT;
see [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md). The tools are also
available as an MCP stdio server: `cobol-archaeologist-mcp`
([docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

## Repository layout

```text
src/cobol_archaeologist/
  ingest/ parser/ static_analysis/   program analysis
  tools.py tool_types.py             the tool layer
  model/                             verifier, GnuCOBOL harness, class policy text
  agent/                             D1-D7 evidence guards, trajectories, stub tools
  eval/                              codex transport, bridge, detector, baseline, runner, report
  benchmark/                         mutation, build, judging, splits, freeze
  rag/                               regulation chunking and retrieval
  migration/                         patch generation and validation
  mcp_server/                        tools over MCP
data/benchmark/                      train/dev/test, temporal pairs, seed programs
data/eval/                           current results and reports
docs/                                architecture, annotation protocol, task records
```

## Corpora and licences

AWS CardDemo (Apache-2.0) is the anchor corpus and IBM CICS CBSA (EPL-2.0) is
secondary; both are fetched at pinned commits, never vendored. Code is MIT
licensed. Regulation metadata identifies source documents; it does not grant
redistribution rights in them.
