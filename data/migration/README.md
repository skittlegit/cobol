# Migration data

- `cases.jsonl` — the four migration cases (benchmark rows with a verified
  finding, the allowed edit scope, and the intended and regression behaviour).
- `detector-visible-candidates.jsonl`, `oracle-candidate-specs.jsonl` — the
  inputs those cases were built from.
- `generation/` — the patch each case produced, the source it was applied to,
  and the WSL GnuCOBOL validation of every patch.
- `report.json`, `report.md` — results: four patches, all passing validation.

Task M1 simplifies these files and the migration code.
