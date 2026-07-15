# BACKLOG — deferred technical debt & future work

Real, verified work items deliberately **not scheduled** yet. This is neither the
task ledger (`STATUS.md`, authoritative for tracked-task state) nor the
cross-track message ledger (`FLAGS.md`, per-track inboxes). An item lives here
when it has no owning task/work order yet or is intentionally postponed; it
leaves when it becomes a work order or rides the commit that resolves it.

Session-start protocol: skim this alongside `STATUS.md` and `FLAGS.md`.

Format per item: **ID** — title · source · owner · trigger (when to pick it up).

## Open

### BL-2 — Wheel / package-data relocatability · source: review F9 · owner: packaging (A+C+pyproject) · trigger: before any wheel/sdist distribution
`src/cobol_archaeologist/parser/_grammar.py` and `rag/chunker.py` resolve the
vendored grammar and regulation data from the **repo root** — outside the Python
package and undeclared in `pyproject.toml`. `pip install -e .` works from a
checkout, but a built wheel would omit the COBOL grammar and regulation data.
Move required runtime assets under the package or declare package-data /
`importlib.resources`. Cross-track, so needs a coordinated packaging pass.

### BL-3 — Repo-wide `ruff format` sweep · source: review H2 · owner: all tracks · trigger: a coordinated quiet window
`ruff format --check` flags ~22 files. A single sweep is a large diff touching
every track's modules at once; land it as one sanctioned commit, or per-track
(each track formats only its own files), to avoid ownership churn. `ruff check`
is already clean.

### BL-4 — CI workflow (pytest + ruff) · source: review F3 · owner: infra · trigger: soon
No PR CI exists. Add `.github/workflows/ci.yml` running `pytest` (network tests
already excluded by default) + `ruff check` (+ optionally `ruff format --check`)
on PRs to `master`. Also confirm the tracked branch-protection / ruleset JSONs
were actually installed in GitHub repo settings — they enforce nothing by merely
existing in the tree.

## Done / promoted

### BL-1 — MO operator coverage for T2.2 · resolved by T2.2

Gate A now covers MO-0…MO-6 plus MO-1×/MO-3×/MO-6×. Clause targeting
tokens use the canonical multiplication sign; CC-29 carries the bridge-backed
MO-4 reference-list host, and the natural CC-06b-v/CC-09b-ii loci carry the
MO-3×/MO-6× variants. MO-0 remains the mandatory global benign pass.

### BL-5 — Independent benchmark bases for non-empty dev · promoted to T2.3b/T2.6b

The v1-pre purpose failure is now scheduled by
`docs/tasks/T2.3b-T2.6b-corrective-work-order.md`: expand independent bases,
repair zero-emission MO-1×/MO-6×, re-judge new rows, and regenerate the split
without relaxing group-preservation or real-curated-test-only rules.
