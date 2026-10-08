# Reproducibility

## Environment

- Python 3.12, `pip install -e ".[dev,models]"`.
- Corpora: `bash scripts/fetch_corpora.sh` (CardDemo pinned in
  `data/manifest.json`).
- GnuCOBOL 3.2.0 for compile/behaviour checks: `bash scripts/setup_cobc.sh`
  (on Windows, inside WSL).
- Model runs: WSL Ubuntu with the Codex CLI logged in through ChatGPT at
  `~/.local/bin/codex-x86_64-unknown-linux-musl` and `uv` at
  `~/.local/bin/uv`. `eval/codex.py` installs the current source into a WSL
  venv keyed by its content hash on first use.

## Offline checks

```bash
pytest tests/ -q
ruff check .
```

## Re-score existing results

```bash
python -m cobol_archaeologist.eval.report --split test
```

This rebuilds `data/eval/test/report.{json,md}` from the committed result
files. It needs no model calls.

## Re-run a system

```bash
python -m cobol_archaeologist.eval.runner detector --split dev --workers 3
python -m cobol_archaeologist.eval.runner rag_reranker --split test
python -m cobol_archaeologist.eval.runner detector --split temporal
```

Each record stores a `run_key` that binds the system, prompt version, model,
effort, runtime source hash, row, and materialized source. Rows whose key
matches are kept; everything else is re-run and replaced in place.

## What is fixed

- Splits: `data/benchmark/{train,dev,test}.jsonl`, hashed in
  `data/benchmark/splits.manifest.json`.
- Temporal pairs: `data/benchmark/temporal/`.
- Gates and statistics seeds: `eval/report.py`.
- Grammar, corpora, and regulation pins: `CLAUDE.md` and `data/manifest.json`.
