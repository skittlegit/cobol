# Migration data

One directory per case:

- `case.json` — the verified finding (`finding_source`: `oracle` or
  `detector`), the edit scope, the intended behaviour, the behaviour fixtures,
  and source assertions.
- `sources/` — the original program and copybook files.
- `patch.diff`, `patch.json` — the generated patch and its rationale.
- `validation.json` — the GnuCOBOL validation result.

`report.json` / `report.md` summarize every case. Regenerate with
`python -m cobol_archaeologist.migration.run validate` (in WSL).
