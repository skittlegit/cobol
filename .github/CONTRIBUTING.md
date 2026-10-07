# Contributing to COBOL Archaeologist

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
This is pre-release research software; accuracy, provenance, and original-source
line fidelity come before speed. Findings are advisory, not legal or compliance
advice.

## Before starting

1. Read [STATUS.md](../STATUS.md) and the task record under
   [`docs/tasks/`](../docs/tasks/).
2. Read [CLAUDE.md](../CLAUDE.md) for the working rules and locked decisions,
   and [docs/architecture.md](../docs/architecture.md) for how the pieces fit.
3. If no task covers your change, open a task issue.

## Setup

```bash
git clone https://github.com/skittlegit/cobol.git
cd cobol
python -m pip install -e ".[dev,models]"
bash scripts/fetch_corpora.sh
```

GnuCOBOL 3.2.0 (`bash scripts/setup_cobc.sh`) is needed only for
compiler-backed tests. It is the behaviour oracle, never the parser; CICS
programs are not expected to compile.

## Making a change

- Branch from `master`, keep the change scoped to one task, and merge back.
- Write the test first for new behaviour.
- Keep one version of everything: no copies, versioned directories, or
  parallel implementations. Regenerated outputs overwrite in place.
- Update `STATUS.md` and the task record in the same commit.
- Commit subjects start with the task ID, for example `D4: add reachability tool`.
- A change to `schemas.py` must update every consumer and its tests together.

## Checks

```bash
python -m ruff check .
python -m pytest tests/ -q
```

For regulation-source changes also run
`python scripts/pin_regulations.py --check`.

## Reporting security issues

Use GitHub's
[private vulnerability reporting form](https://github.com/skittlegit/cobol/security/advisories/new)
and follow the [security policy](SECURITY.md). Do not open a public issue.
Treat `run_cobol` as an arbitrary-code-execution boundary: run untrusted COBOL
only in an isolated environment with no secrets or outbound network.

## Licensing

Contributions are distributed under the [MIT License](../LICENSE). Submit only
work and data you have the right to contribute, and keep required third-party
notices.
