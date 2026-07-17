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

### BL-6 — Re-adjudicate T2.4 on the current 591-row catalogue (reopen M2) · source: audit H2 · owner: B · trigger: now — blocks headline eval
The closing T2.4 evidence (98% on a 50-sample, 301/311 full) was judged on the
**pre-T2.3b 311-row** catalogue. The current catalogue is **591 rows**
(regenerated in `1bce6b9`); its own full `gpt-5.6-luna`/high run in
`data/benchmark/drift_instances.manifest.json:78` records **`gate_passed: false`
at 89.51%** with **5 `unsure` left unadjudicated**, and the historical 50-sample
overlaps the current IDs by only 1/50. T2.4 requires human adjudication of
`unsure` (`T2.4-work-order.md:29`) and T2.6 requires T2.4's gates green
(`T2.6-work-order.md:17`). Resolve by either (a) adjudicating the 5 cases and
running a current-catalogue stratified 50-sample to ≥90%, or (b) formally
amending the work order to permit conservative exclusion + historical-sample
reuse. Until then M2's PASSED is provisional (see the STATUS M2/T2.4 caveats).

### BL-7 — `run_cobol` path-escape + unbounded output collection · source: audit H1 · owner: A · trigger: soon — before MCP self-host (T7.1)
`RunInputs.files` names are joined straight onto the temp dir and written
without validation (`model/run_cobol.py:174-177`); an absolute path or `../`
name escapes the sandbox dir and can overwrite files before compile. Output
collection (`run_cobol.py:234`) then reads **every** generated file with no
size/count cap. SECURITY.md already treats `run_cobol` as an ACE surface needing
an external sandbox, but the in-process temp-dir guarantee is still breachable.
Reject absolute/traversal names, resolve-and-contain under the tmpdir, and cap
collected output count + bytes. Track A owns the module.

### BL-8 — Benchmark manifest records the wrong generating commit · source: audit M3 · owner: B · trigger: with the BL-6 regeneration
`drift_instances.manifest.json:70` stamps `git_sha` `f880b6e`, but the
generator/operator changes and corpus regeneration landed in `1bce6b9`.
Reconstructing from the recorded SHA cannot reproduce the catalogue. Stamp the
actual generating HEAD; naturally fixed when BL-6 regenerates, but flag it so a
stale SHA is not carried forward again.

### BL-9 — Reconcile the locked GnuCOBOL version · source: audit M4 · owner: infra (touches CLAUDE.md locked decision #3) · trigger: team decision
CLAUDE.md decision #3 locks GnuCOBOL **3.1.2**, but STATUS T1.5/T2.2 record
validation on **3.2.0** and `scripts/setup_cobc.sh:15` installs whatever
`gnucobol3` apt currently ships. Pick one version of record and enforce it (pin
the setup script, or amend the locked decision). CLAUDE.md locked-decision edits
are a team call, not a unilateral fix — hence backlog, not a direct edit.

### BL-10 — Split repair can report false infeasibility · source: audit M5 · owner: B · trigger: when a 2-move split need arises
The repair loop at `benchmark/splits.py:278` only accepts a move that
*immediately* reduces the failed-gate count (`len(candidate_errors) >=
len(errors): continue`), so a feasible solution needing two intermediate moves
is rejected as infeasible. Use quantitative deficit scoring or a bounded
constrained search, and add a multi-move fixture. The current corpus passes, so
this is latent.

### BL-11 — Security / review governance gaps · source: audit M6 · owner: infra · trigger: before benchmark/v1 (T5.2) or MCP ship (T7.1)
Three items: (a) `SECURITY.md:27` still has the `<security-contact@REPLACE-ME>`
placeholder; (b) the frozen contract shape `tool_types.py` has **no** CODEOWNER
entry and `schemas.py`'s CODEOWNERS line omits Track A (`@twiswiz`); (c) the
branch-protection rulesets in `.github/rulesets/` enforce nothing unless actually
installed in GitHub settings (see also BL-4). Fill the contact, add the missing
code-owners, and confirm required review is live.

### BL-12 — Runnable-base provenance stale in the manifest · source: audit M7 · owner: B · trigger: with the next manifest bump
`data/manifest.json:58-61` still lists the runnable base with `pinned_commit:
null` and "Selection and pinning due at T1.5/T2.5 start", though both tasks and
the native bases (`OVRLIM1.cbl`, `CLOSPEN5.cbl`, …) are authored and in use.
Update the role notes and pin, or document that the bases are repo-native and
need no external pin.

### BL-13 — Chunker emits duplicate `clause_id` `5(xiv)` (OVD vs REs) · source: T2.4b reconciliation · owner: C · trigger: before T2.4b/M2 re-closure
`rag/chunker.py::build_all_chunks()` produces **two** chunks with
`clause_id='5(xiv)'` for RBI-KYC-Directions-2025 — the genuine OVD definition
(page 8) and a mislabeled "Regulated Entities (REs)" item (page 12). This fails
`test_chunker::test_gate_a_clause_records_reconcile_to_exactly_one_chunk` for the
new D4 anchor `KYC-ovd-list` (whose text overlaps the page-8 OVD chunk at 1.0).
The clause is correct; the chunker must dedup/disambiguate the page-12 `(xiv)`
label. Only this one gate is red — the drift catalogue and judging are
unaffected. Flagged to Track C (FLAGS 2026-07-16). Gate goes green the moment
the dup is removed; no Track B change needed.

### BL-14 — MO-0 is not a matched control (Gate E) · source: T2.4b Gate E · owner: B (escalated to C) · trigger: T2.4/T5.5 probe-design review
**Owner:** B · **Severity:** High · **Status:** improved 0.757 -> 0.6537, still
red. Escalated to Track C as a probe-design review item (Gate E re-runs at
T2.4/T5.5 under their eval ownership). Full arc in
`docs/tasks/T2.4b-readjudication-work-order.md` BLOCKER B1.

`test_gate_e_surface_probe_sample_is_at_chance` fails at AUC 0.757 (CI
0.684–0.824) on seed 2601: D1 mutants are separable from their D7 pairs by
surface features alone (CLAUDE.md #7). Driven by `diff_size` (0.678) and
`literal_roundness` (0.545) — the grid's stale values change digit width and
divisible-by-5 status one-directionally, while MO-0's control edit only nudges a
DISPLAY string.

The old `current * 1.1` fallback passed this gate **by accident** (it preserved
digit width and shared a leading digit). The real defect is that MO-0 is not a
matched control. Fix is an integrity-rule-level decision — see BLOCKER B1 in
`docs/tasks/T2.4b-readjudication-work-order.md`. Do not judge until resolved.

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
