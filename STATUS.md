# STATUS

One entry per task: ID, state, owner, and artifact.

- **T0.1** | done | B |
  `data/manifest.json`
  v1.1: CC Directions widening; CardDemo pinned at `59cc6c2`.
- **T0.2** | done | B |
  `docs/tasks/T0.2-taxonomy-examples.md`
  fit: CC Directions 2022 plus KYC 2025 via clause 20.
- **T0.3** | done | C |
  `src/cobol_archaeologist/schemas.py` + `tests/test_schemas.py`.
  SCHEMA FROZEN — changes hereafter are CONTRACT CHANGEs (flag to A/B/C).
- **T0.4** | wip | C |
  Fully unblocked. Tool half from Track A brief section T1.6; metrics half
  unblocked by T0.2.
- **T0.5** | done | A |
  `docs/tasks/T0.5-ast-decision-note.md`.
- **T0.6** | todo | C |
  `docs/track-c-brief.md` section T0.6. No dependencies; start any time.
- **T1.0** | done | A |
  `pyproject.toml` + `src/cobol_archaeologist/` skeleton +
  `vendor/tree-sitter-cobol/` (pinned `e99dbdc`) + `scripts/fetch_corpora.sh` +
  `tests/test_scaffold.py` (gate green on Python 3.12 / tree_sitter 0.21.3).
- **T1.1-T1.6** | todo | A |
  `docs/track-a-brief.md`. Unblocked by T1.0.
- **T2.1** | todo | B |
  Scope follows the T0.2 contract change. Re-verify CC amendments at curation.
- **T2.2-T2.4, T2.6** | todo | B |
  `docs/track-b-brief.md`. T2.2 is blocked on T1.4, T1.5, and T2.1.
- **T2.5** | todo | B |
  Start early; runs in background. Dependencies: T0.3 freeze and T2.1.
- **T3.1-T3.6** | todo | C |
  `docs/track-c-brief.md`. Stub-based, not blocked on Track A.
- **T4.x-T7.x** | todo | A/B/C |
  Per playbook Part 4; not yet in play.
