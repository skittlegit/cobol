# Fix-now — safe, do-immediately (mostly Track B + trivial hygiene)

Each item is low-risk, needs no cross-track decision, and can land on your
branch. Column "coord" flags the two that touch shared config (still safe, just
worth a heads-up in chat).

## 1. F4 — stale regulatory provenance (Track B owns) · coord: none

**clauses.jsonl** — 15 CC records still say the mapping is secondary. Phase 2
primary-confirmed them (zero corrections).

```bash
grep -n "secondary-mapped" data/regulations/clauses.jsonl   # 15 hits, all CC
```
Replace the provenance/verification phrasing on those records, e.g.
`"2025 para secondary-mapped; primary pass at T2.5"` →
`"primary-confirmed against cc-dc-directions-2025.pdf (T2.5 Phase 2, zero corrections)"`.
Keep `record_id`/`clause_id`/`clause.text` untouched (a text change would ripple
into the frozen retrieval corpus). Re-run `pytest tests/test_clauses.py`.

**data/manifest.json:32** — two stale claims:
- `"KYC clause_ids in clauses.jsonl remain PROVISIONAL pending the primary read
  … at T2.5"` → resolved: **42(1)** (periodic-updation), **5(iv)(b)**
  (BO-partnership), **65(8)** (CKYCR).
- `"Pure-KYC logic … is implemented in the GnuCOBOL-native runnable base"`
  contradicts line 61 (`"Selection and pinning due at T1.5/T2.5 start"`) and the
  fact that `run_cobol.py` is a stub. Soften to `"will live in"` / `"planned
  for"` so lines 32 and 61 agree.

## 2. H7 — `scripts/pin_regulations.py:18` (Track B) · coord: none

`"drop the seven files named"` → `"eight files"` (we added
`kyc-md-2016-consol-pre-2023-10.pdf` to `EXPECTED`).

## 3. H1 — ruff unused import (trivial) · coord: none

```bash
ruff check --fix tests/test_clauses.py   # removes the unused `import pytest`
```

## 4. H3 — network tests excluded by default (pyproject) · coord: light (C)

In `[tool.pytest.ini_options]` add `addopts = "-m 'not network'"` so the README's
plain `pytest` never downloads model weights once `sentence-transformers` is
installed. Document the model run separately, e.g. `pytest -m network`. (We
already guard individual network tests with `importorskip`; this makes the
default suite intent explicit.)

## 5. H4 — README stale (docs) · coord: none

- `README.md:~48` points to the removed `src/cobol/spike_parser.py` — repoint to
  the real parser (`src/cobol_archaeologist/parser/`) or drop the line.
- `README.md:~55` says packaging hasn't landed — it has (`pyproject.toml`,
  `pip install -e .` works). Update.

## 6. H5 — `docs/branching.md` main/master (docs) · coord: light (all)

Normalize `main`→`master` throughout and reconcile the per-task-branch vs
permanent-track-branch wording with `CLAUDE.md` + `docs/team-workflow.md`
(they treat `track-a|b|c` as permanent).

## 7. F3 (safe parts) — GitHub automation file placement · coord: light (infra)

Pure file moves + a branch-name fix; no logic:
- `git mv .github/codeql.yml .github/workflows/codeql.yml`
- in it: `main` → `master`; remove/repoint the nonexistent
  `.github/codeql/codeql-config.yml` reference.
- `mkdir -p .github/ISSUE_TEMPLATE && git mv .github/task.yml .github/config.yml
  .github/ISSUE_TEMPLATE/`

**Not in this file** (needs a real authoring pass, small task): add a
`ci.yml` running `pytest -m "not network"` + `ruff check` + `ruff format
--check` on PRs. And confirm the tracked ruleset JSONs were actually installed
in GitHub repo settings — they enforce nothing by merely existing in the tree.

## Verify after

```bash
pytest tests/test_clauses.py tests/test_sources.py -q
ruff check .                       # H1 clears
python -c "import json;json.load(open('data/manifest.json'))"   # manifest valid
```
