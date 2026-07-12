# BACKLOG — deferred technical debt & future work

Real, verified work items deliberately **not scheduled** yet. This is neither the
task ledger (`STATUS.md`, authoritative for tracked-task state) nor the
cross-track message ledger (`FLAGS.md`, per-track inboxes). An item lives here
when it has no owning task/work order yet or is intentionally postponed; it
leaves when it becomes a work order or rides the commit that resolves it.

Session-start protocol: skim this alongside `STATUS.md` and `FLAGS.md`.

Format per item: **ID** — title · source · owner · trigger (when to pick it up).

## Open

### BL-1 — MO operator coverage for T2.2 · source: review F1b · owner: B · trigger: T2.2 authoring (after T1.5)
T2.2 Gate A requires MO-0…MO-6 plus the interprocedural variants
**MO-1× / MO-3× / MO-6×**. `data/regulations/clauses.jsonl` today carries
MO-1(13), MO-1x(2, ASCII `x`), MO-2(6), MO-3(5), MO-5(13), MO-6(3). Gaps:
**MO-4** absent, **MO-3× / MO-6×** absent, and the two `MO-1x` use ASCII `x`
where the spec uses `×` (normalize). MO-0 is the mandatory *global* benign edit,
not a per-record token — its absence from `mutation_ops` is expected. Do this as
part of the T2.2 work order, not standalone; T2.2 is blocked on T1.5.

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

(none yet — move an item here with the resolving commit or work-order id when it closes)
