# Contributing to COBOL Archaeologist

Thank you for contributing code, tests, documentation, benchmark data, or
reproducibility improvements. By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

COBOL Archaeologist is pre-release research software. Accuracy, provenance,
and original-source line fidelity take priority over implementation speed.
Findings are advisory and require expert review; they are not legal or
compliance advice.

## Before starting

1. Check the authoritative [task ledger](../STATUS.md), the
   [open backlog](../BACKLOG.md), and active [cross-track flags](../FLAGS.md).
2. Search existing issues and pull requests to avoid duplicate work.
3. Read [CLAUDE.md](../CLAUDE.md), the
   [team workflow](../docs/team-workflow.md), and the task's canonical work
   order under [`docs/tasks/`](../docs/tasks/).
4. Open a task issue if no suitable task or work order exists.

Substantive work is organized by task ID. Each task has exactly one canonical
file named `docs/tasks/T<n>.<n>-work-order.md`; do not create parallel briefs,
reports, or repair sidecars. If repository records conflict, stop and ask a
maintainer to reconcile them rather than choosing silently.

Do not report vulnerabilities publicly. See
[Reporting security issues](#reporting-security-issues).

## Ownership and contracts

| Track | Area |
|---|---|
| A | Preprocessing, parsing, static analysis, runtime harness, and ToolLayer |
| B | Regulation curation, benchmark generation/judging, data, and splits |
| C | Frozen schemas, retrieval, verification, agent orchestration, and evaluation |

The exact mapping is in [CODEOWNERS](CODEOWNERS). Do not modify another track's
owned module as a convenience; raise the dependency for its owner.

A semantic change to `src/cobol_archaeologist/schemas.py`, the ToolLayer models
or signatures, or `docs/CONTRACT.md` is a **CONTRACT CHANGE**. Document the
proposal and obtain the required Track A/B/C sign-offs before implementation.

## Development setup

The project requires Python 3.12 (`>=3.12,<3.13`).

```bash
git clone https://github.com/skittlegit/cobol.git
cd cobol
python -m pip install -e ".[dev]"
bash scripts/fetch_corpora.sh
```

The fetch script downloads commit-pinned AWS CardDemo and IBM CICS CBSA
sources into `data/corpora/`; do not vendor them.

The default test configuration is offline. Model-backed retrieval gates are
explicit:

```bash
python -m pip install -e ".[models]"
python -m pytest -m network
```

GnuCOBOL is optional for most work. It is the compile/behavior oracle, never
the parser, and CICS sources are not expected to compile under it.

## Making a change

1. Work on the owning permanent branch: `track-a`, `track-b`, or `track-c`.
   External contributors should ask the owning maintainer which branch to
   target from their fork.
2. Update the track branch by merging `master`; do not rebase shared branches.
3. Read the work order and write its acceptance gate before implementation.
4. Keep the diff within the documented scope and ownership boundary.
5. Preserve original-source line maps and the locked decisions in
   [CLAUDE.md](../CLAUDE.md).
6. Update the task's `STATUS.md` line in the same commit as the implementation
   or completion evidence.
7. Remove temporary outputs after recording durable evidence in the canonical
   work order or artifact.

Code and data contributions must also:

- use structured, bounded tool results with original-source pointers;
- avoid unrelated formatting and generated files;
- preserve document versions, effective dates, hashes, seeds, and model
  identity where they affect reproducibility;
- prefer primary regulatory sources and never silently substitute a secondary
  source; and
- use the real validation toolchain for gate evidence rather than a simulated
  probe.

## Tests and quality gates

Run the task-specific gate and all relevant prior gates. Unless the work order
specifies a narrower environment, run:

```bash
python -m ruff check .
python -m pytest tests/ -x -q
python -m build
```

For regulation-source changes, also run:

```bash
python scripts/pin_regulations.py --check
python -m pytest tests/test_sources.py tests/test_clauses.py -q
```

State external dependencies and intentional skips explicitly. A skipped or
simulated check is not completed evidence.

## Commits and pull requests

- Prefix task commits with the task ID, for example
  `T3.2: refresh retrieval evidence`.
- Keep commits focused and include the matching `STATUS.md` transition.
- Do not force-push, rebase shared permanent branches, or push implementation
  commits directly to `master`.
- Integrate reviewed track work into `master` with a merge commit.

Use the pull request template. Include the task, track, work order, reason for
the change, acceptance evidence, commands run, `STATUS.md` transition, contract
impact, and any reproducibility or provenance changes. Keep the branch current
with `master` by merge and resolve every actionable review thread.

Approval must come from a different track. Reviewers should clone the pushed
branch and run the relevant gates instead of relying only on pasted output.

## Reporting issues

Use the task issue form and provide the affected commit, environment, minimal
reproduction, expected and actual behavior, relevant files, and proposed
acceptance criteria. For benchmark concerns, include instance IDs, clause IDs,
source loci, and provenance without posting private material.

## Reporting security issues

Use GitHub's
[private vulnerability reporting form](https://github.com/skittlegit/cobol/security/advisories/new)
and follow the [security policy](SECURITY.md). Do not open a public issue.

Treat `run_cobol` as an arbitrary-code-execution boundary. Run untrusted COBOL
only in an isolated environment with no secrets or outbound network, strict
resource limits, and an ephemeral or read-only filesystem.

## Licensing

Contributions are distributed under the project's [MIT License](../LICENSE).
Submit only work and data that you have the right to contribute, and retain
required third-party notices.
