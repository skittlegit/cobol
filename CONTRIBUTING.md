# Contributing to COBOL Archaeologist

Thank you for helping improve COBOL Archaeologist. Contributions may include
code, tests, documentation, benchmark data, regulation-source corrections, and
reproducibility improvements.

This is a pre-release research project for detecting possible regulatory drift
in legacy COBOL. Accuracy, provenance, and original-source line fidelity matter
more than implementation speed. Project findings are advisory and require
expert review; they are not legal or compliance advice.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

1. Check [STATUS.md](STATUS.md) for authoritative task state.
2. Check [BACKLOG.md](BACKLOG.md) for verified but unscheduled work.
3. Check [FLAGS.md](FLAGS.md) for active cross-track dependencies.
4. Search existing issues and pull requests to avoid duplicate work.
5. Read [CLAUDE.md](CLAUDE.md), the relevant canonical work order under
   [`docs/tasks/`](docs/tasks/), and the
   [team workflow](docs/team-workflow.md).

Substantive work is organized by task ID and must have exactly one canonical
work order named `docs/tasks/T<n>.<n>-work-order.md`. The work order contains
the task's accepted scope, amendments, acceptance gates, and durable evidence.
Do not create parallel briefs, repair files, reports, or other task sidecars.

If no suitable task or work order exists, open a task issue before implementing
the change. For a small typo or clearly mechanical documentation correction,
describe the limited scope in the pull request and confirm the appropriate
target branch with a maintainer.

Do not open a public issue for a vulnerability. Follow
[Reporting security issues](#reporting-security-issues) instead.

## Repository governance

### Sources of truth

The repository records have explicit responsibilities:

- [STATUS.md](STATUS.md) alone determines whether a task is `todo`, `wip`,
  `blocked`, or `done`.
- [FLAGS.md](FLAGS.md) is the current cross-track inbox.
- [BACKLOG.md](BACKLOG.md) contains verified work that is not yet scheduled.
- A task's canonical work order governs that task and takes precedence over
  repository-wide guidance.
- [docs/CONTRACT.md](docs/CONTRACT.md) governs shared interfaces and evaluation
  definitions.
- [CLAUDE.md](CLAUDE.md) records repository-wide invariants, pins, ownership,
  and standard commands.

If these records conflict, stop and ask maintainers to reconcile them. Do not
silently choose one interpretation.

### Ownership tracks

Development is divided into three permanent tracks:

| Track | Area |
|---|---|
| A | Preprocessing, parsing, static analysis, the runtime harness, and the real ToolLayer |
| B | Regulation curation, benchmark mutation/build/judging, benchmark data, and splits |
| C | Frozen schemas, retrieval, verification, agent orchestration, and evaluation |

The detailed file-to-owner mapping is in
[`.github/CODEOWNERS`](.github/CODEOWNERS). Do not modify another track's owned
module as a convenience. Raise the dependency so the owning track can address
it.

### Contract changes

A semantic change to any of the following is a **CONTRACT CHANGE**:

- `src/cobol_archaeologist/schemas.py`;
- ToolLayer models or method signatures in
  `src/cobol_archaeologist/tool_types.py` and the corresponding implementation;
- `docs/CONTRACT.md`.

Stop implementation, document the proposal, obtain the required Track A/B/C
sign-offs, and update the contract and affected work orders before changing the
code. Documentation cleanup must not silently change contract semantics.

## Development setup

The project targets Python 3.12 (`>=3.12,<3.13`).

```bash
git clone https://github.com/skittlegit/cobol.git
cd cobol
python -m pip install -e ".[dev]"
bash scripts/fetch_corpora.sh
```

`scripts/fetch_corpora.sh` fetches commit-pinned AWS CardDemo and IBM CICS CBSA
sources into `data/corpora/`. These corpora are intentionally not vendored.

The default test configuration is offline and excludes tests marked `network`.
For model-backed retrieval gates:

```bash
python -m pip install -e ".[models]"
python -m pytest -m network
```

Model weights may require network access on first use. Never send proprietary
COBOL or private regulation material to an external service without explicit
authorization and an appropriate data-processing agreement.

GnuCOBOL is optional for most development. Tests requiring `cobc` skip when it
is unavailable. GnuCOBOL is the compile/behavior oracle only; it is never the
parser, and CICS sources are not expected to compile under it.

## Making a change

1. Work from the permanent branch that owns the task: `track-a`, `track-b`, or
   `track-c`. If you do not have permission to push to that branch, fork the
   repository and ask the owning maintainer which branch your pull request
   should target.
2. Bring the track branch up to date by merging `master`. Do not rebase shared
   permanent branches.
3. Read the task work order and write the acceptance gate before the
   implementation.
4. Keep the change within the owning track and the documented scope.
5. Preserve original-source line mapping and all locked decisions in
   [CLAUDE.md](CLAUDE.md).
6. Update the task's line in [STATUS.md](STATUS.md) in the same commit as the
   implementation or completion evidence.
7. Add a flag only when another track has a concrete action or must acknowledge
   a shared-interface change.
8. Remove temporary outputs once durable evidence has been recorded in the
   canonical work order or artifact.

### Code expectations

- Use Python 3.12 and add type information where it improves the public or
  inter-module contract.
- Use Pydantic models for structured inter-module data.
- Preserve the line-count and line-map invariants through preprocessing and
  copybook expansion.
- Keep tool output structured and bounded, with original-source pointers rather
  than unbounded raw dumps.
- Do not edit the vendored tree-sitter COBOL grammar or change its pin without
  the required parser validation gate.
- Do not vendor fetched corpora, model caches, generated checkpoints, or
  temporary judge output.
- Record source versions, effective dates, hashes, seeds, and model identity
  when they affect reproducibility.

### Data and regulation contributions

Benchmark and regulation changes require the same review discipline as code:

- prefer primary regulatory sources;
- preserve document version and effective-date information;
- pin archived source bytes in `data/regulations/sources/MANIFEST.json`;
- never replace a missing primary source silently with a secondary copy;
- preserve base-program grouping and other split-leakage constraints; and
- run the real build/validation toolchain for evidence—lightweight probes may
  generate hypotheses but cannot close a gate.

Verify pinned regulation sources with:

```bash
python scripts/pin_regulations.py --check
python -m pytest tests/test_sources.py tests/test_clauses.py -q
```

## Tests and quality gates

Run the task-specific gate from its work order and all relevant prior gates.
Unless the work order defines a narrower environment gate, run:

```bash
python -m ruff check .
python -m pytest tests/ -x -q
python -m build
```

The full offline suite and Ruff check also run in GitHub Actions. Repository-wide
formatting is currently coordinated separately; avoid unrelated formatting
changes that obscure the functional diff.

When a test needs an external compiler, model, or network service, make that
dependency explicit. Do not present a skipped or simulated check as completed
evidence.

## Commits and branches

- Prefix task commits with the task ID, for example:
  `T3.2: refresh retrieval evidence`.
- Keep each commit reviewable and limited to one coherent purpose.
- Carry the corresponding `STATUS.md` update in the implementation/evidence
  commit rather than in a later cleanup commit.
- Do not force-push or rebase shared permanent branches.
- Do not push implementation commits directly to `master`.
- Use merge commits when integrating reviewed track work into `master`.

## Pull requests

Use the repository's pull request template and include:

- the task ID, owning track, issue, and canonical work order;
- a concise explanation of what changed and why;
- the exact `STATUS.md` transition;
- the applicable “done when” criteria and evidence;
- commands run and their outcomes, including intentional skips;
- explicit contract impact;
- data/provenance changes, when applicable; and
- any `# DECISION:` comments introduced to resolve implementation ambiguity.

Before requesting review:

- keep the source branch current with `master` by merge, not rebase;
- review the complete diff for unrelated or generated files;
- run the relevant gates from a clean checkout when practical; and
- make sure documentation, tests, and source pointers agree with the final
  behavior.

Approval must come from a different track. Reviewers should clone the pushed
branch and run the relevant gates rather than relying only on pasted output.
Resolve every actionable review thread before merge.

## Reporting bugs and proposing work

Use the repository's task issue form. Include:

- the affected commit and environment;
- the owning track, if known;
- minimal reproduction steps or a focused example;
- expected and actual behavior;
- affected source/data files; and
- proposed acceptance criteria.

For benchmark-quality concerns, include the affected instance IDs, clause IDs,
source loci, and provenance without posting private code or documents.

## Reporting security issues

Do not report vulnerabilities in a public issue, discussion, or pull request.
Use GitHub's
[private vulnerability reporting form](https://github.com/skittlegit/cobol/security/advisories/new)
and follow [SECURITY.md](SECURITY.md).

Treat `run_cobol` as an arbitrary-code-execution boundary. Reproductions that
compile or execute untrusted COBOL must run in an isolated environment with no
secrets, no outbound network, resource limits, and an ephemeral or read-only
filesystem.

## Licensing

By submitting a contribution, you agree that it may be distributed under the
project's [MIT License](LICENSE). Submit only work and data that you have the
right to contribute, and retain required notices for third-party material.

Thank you for helping make the system accurate, reproducible, and useful.
