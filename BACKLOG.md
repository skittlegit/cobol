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

### BL-7 — `run_cobol` path-escape + unbounded output collection · source: audit H1 · owner: A · trigger: soon — before MCP self-host (T7.1)
`RunInputs.files` names are joined straight onto the temp dir and written
without validation (`model/run_cobol.py:174-177`); an absolute path or `../`
name escapes the sandbox dir and can overwrite files before compile. Output
collection (`run_cobol.py:234`) then reads **every** generated file with no
size/count cap. SECURITY.md already treats `run_cobol` as an ACE surface needing
an external sandbox, but the in-process temp-dir guarantee is still breachable.
Reject absolute/traversal names, resolve-and-contain under the tmpdir, and cap
collected output count + bytes. Track A owns the module.

### BL-9 — Reconcile the locked GnuCOBOL version · source: audit M4 · owner: infra (touches CLAUDE.md locked decision #3) · trigger: team decision
CLAUDE.md decision #3 locks GnuCOBOL **3.1.2**, but STATUS T1.5/T2.2 record
validation on **3.2.0** and `scripts/setup_cobc.sh:15` installs whatever
`gnucobol3` apt currently ships. Pick one version of record and enforce it (pin
the setup script, or amend the locked decision). CLAUDE.md locked-decision edits
are a team call, not a unilateral fix — hence backlog, not a direct edit.

### BL-10 — Split repair can report false infeasibility · source: audit M5 · owner: B · trigger: T2.6 regeneration
The repair loop only accepts a move that immediately reduces failed-gate count,
so a feasible solution needing two whole-group moves can be rejected. T2.6 must
add quantitative deficit scoring plus a multi-move regression if the corrected
accepted catalogue triggers the defect; no purpose gate may be relaxed.

### BL-11 — Security / review governance gaps · source: audit M6 · owner: infra · trigger: before benchmark/v1 (T5.2) or MCP ship (T7.1)
Three items: (a) `SECURITY.md:27` still has the `<security-contact@REPLACE-ME>`
placeholder; (b) the frozen contract shape `tool_types.py` has **no** CODEOWNER
entry and `schemas.py`'s CODEOWNERS line omits Track A (`@twiswiz`); (c) the
branch-protection rulesets in `.github/rulesets/` enforce nothing unless actually
installed in GitHub settings (see also BL-4). Fill the contact, add the missing
code-owners, and confirm required review is live.

### BL-16 — Local probe harness is not faithful — do not close gates on it · source: T2.4b · owner: B · trigger: standing rule, applies now
**Owner:** B · **Severity:** High (process)

A pure-text harness reproduced the build's Gate E number (0.75715) *exactly*,
and was then trusted through six iterations of MO-0 work. It diverged: it
reported 0.5457 where WSL reports 0.6537, and "Gate E passes" was claimed on
that basis. Cause: the harness has no validation step, so it cannot model
`run_candidate` dropping mutations that fail compilation and thereby changing
the probe's host composition. Validating an instrument once and trusting it
after changing the code it models is the defect.
**Rule:** Gate E's number of record is the WSL build. Local harnesses may
generate hypotheses; they may not close gates.

## Done / promoted

### BL-6 — Re-adjudicate T2.4 on the corrected current catalogue · resolved 2026-07-17
**Owner:** B · **Resolved by:** T2.4b current-catalogue evidence

The final 594-row catalogue passed the fresh Luna/high gate at **50/50 (100%)**
on the stratified sample and **557/594 (93.77%)** raw on the full set. Five
`unsure` rows were independently human-accepted and logged as overrides; the
shipping set is **562 accepted / 32 implausible / 0 unsure**, with a **0.84%**
override rate. The prescribed 15-item review agreed **15/15**. Canonical judge,
drop-policy, review, and manifest evidence now describe the same catalogue.

### BL-18 — Replicated rows can satisfy class floors without semantic diversity · resolved 2026-07-17
**Owner:** B · **Resolved by:** T2.4b corrective catalogue and semantic floor

The superseded 603-row catalogue collapsed 425 D1-D6 rows into only 37 semantic
mutations (D2=2, D4=2, D6=3). The build now requires four structured distinct
mutations per D1-D6 class and records counts/floors/shortfalls in its manifest.
Seven separately authored loci brought the real WSL 594-row build to D1-D6
counts **13/6/5/4/12/7**, with every shortfall zero and every row compiled.
Replication can no longer satisfy a class floor. BL-6's fresh plausibility
evidence is now complete on this catalogue.

### BL-8 — Benchmark manifest records the wrong generating commit · resolved by `cb0442b` + `d35adb6`
**Owner:** B · **Resolved by:** `cb0442b` (guard) + `d35adb6` (regeneration)

The manifest stamped `f880b6e` while the catalogue was generated in `1bce6b9`,
so it could not be reproduced from its own provenance. It now records `cb0442b`,
the HEAD that generated the 603-row catalogue.

**Kept structural, not hardcoded:**
`test_bl8_checked_in_manifest_names_the_head_that_generated_it` handles both
valid workflow states: a newly generated dirty manifest must name current HEAD;
a committed catalogue must name the parent of the commit that first recorded
its non-`judging` state. Later judge-only stamps are intentionally ignored, so
evidence commits cannot make a correct catalogue provenance test turn red.

### BL-12 — Runnable-base provenance stale in the manifest · resolved by `cb0442b`
**Owner:** B · **Resolved by:** `cb0442b`

`data/manifest.json` carried `pinned_commit: null` plus "Selection and pinning
due at T1.5/T2.5 start" long after both tasks shipped and the native bases were
in use. Resolved by **documenting the absence rather than inventing a pin**: the
bases are repo-native (`pin_status: not_applicable_repo_native`), located at
`data/benchmark/seed/programs/**`, enumerated in `base_roster.json`.
`test_bl12_runnable_base_is_repo_native_and_rostered` asserts the roster and a
named base exist on disk, so the note cannot drift from the tree.

**Consistent with the session's lesson:** a null pin was ambiguous between "not
yet done" and "not applicable" — absence read as permission. It now says which.

### BL-13 — Chunker duplicate `5(xiv)` · resolved 2026-07-17

The chunker now preserves numbered definition groups as hierarchy levels. The
KYC second definition group's Regulated Entities entry is structurally distinct
from Track B's curated OVD `5(xiv)` instead of collapsing both local `(xiv)`
labels onto one ID. Gate A and the dedicated nested-definition regression pass.

### BL-14 — Gate E conflated two attacker models · resolved by CONTRACT v1.3

Track C ratified and Track B signed the threat-model split on 2026-07-17. The
artifact-only `literal_roundness` probe remains a hard at-chance bootstrap gate;
the aggregate attacker-with-bases probe is recorded as a mandatory seventh T5.3
baseline and must be cleared by a predeclared margin with paired CIs. Decision:
`docs/reviews/2026-07-17/contract-change-gate-e-RESOLVED.md`.

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

### BL-15 — Floor-shaped clause values carry no `comparator` · resolved by the BL-15 curation pass + `fb621f9`/`0591fa4`
**Owner:** B · **Severity:** Medium · **Resolved by:** `clauses.jsonl` curation
pass (Lead) + `fb621f9` / `0591fa4` (guards)

`_stale_value` picks the stale side from the leaf's `comparator` (`at_least` =
floor = snap down). `CC-08a.penalty_per_day` (₹500/day) is floor-shaped but
declared no comparator, so it read as a ceiling and drifted *up* to ₹1000 — a
stricter penalty, the opposite of drift. `_assert_snap_direction` cannot catch
what the data does not declare.

**It was never one field:** 13 of 21 MO-targetable leaves declared no
comparator, and every one was a composite leaf — comparators were omitted
wherever the value "felt" unambiguous. Resolved on both sides: all 13 now
declare one (7 `at_most` ceilings; `penalty_per_day` `at_least` → ₹500→₹200;
`inactivity_threshold` `strictly_greater`; the 3 KYC intervals `at_most` —
"at least once every N years" is a floor on *frequency* but a ceiling on the
*interval* the leaf stores; `CC-06a-iv` exempt via `check.mo1_mode`), and
absence is now a hard `ClauseDataError` rather than a silent ceiling default.

**Lesson (kept, not archived):** BL-15 existed only because absence was
*interpretable*. The gate proves a comparator is **declared**, not that it is
**right** — a file snapping `penalty_per_day` upward would pass the declaration
gate while being the exact bug. Verification therefore checks resolved snaps
against a ruling stated in advance, not just declaration coverage.

### BL-17 — MO-0 inertness proof missed 88-level aliases · resolved by `c2d004f`
**Owner:** B · **Resolved by:** `c2d004f`

`_inert_numeric_sites` judged a field inert when its *name* never appeared in
the PROCEDURE DIVISION. CLOSPEN5 guards `WS-PEN-ENABLED` with `IF PENALTY-ON`,
an 88-level condition name, so the field read as inert and MO-0 widened a PIC on
a field live logic reads through its alias — a correctness bug in the
*conformant* class, found only because the WSL suite ran. Condition names now
map back to their owner. **Kept as a lesson:** every bug this session was an
absence read as permission — a missing comparator, a missing prior value, a
missing name in a procedure.
