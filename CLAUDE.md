# CLAUDE.md — COBOL Archaeologist

## What this repo is

A system + benchmark for detecting where legacy COBOL banking code has
**drifted** from the financial regulation it was built to satisfy (stale
thresholds, missing checks, contradictions, stale reference data, boundary
errors, dead compliance code), with verified explanations and an optional
migration step. Drift detection is the research contribution; the benchmark is
the moat.

## Document map & precedence

- `STATUS.md` (repo root): the task ledger — one line per task,
  `ID | state | owner | artifact`. **Authoritative for project state.**
- `FLAGS.md` (repo root): cross-track message ledger — per-track inboxes; a flag
  rides the commit of the deliverable that caused it. Read at session start.
- `BACKLOG.md` (repo root): deferred technical debt & future work not yet
  scheduled as a task — distinct from `STATUS.md` (tracked tasks) and `FLAGS.md`
  (messages). An item leaves it when it becomes a work order or is fixed.
- `docs/tasks/T<n>.<n>-work-order.md`: exactly one work order per task. Fold
  corrective/amendment phases, rubrics, reports, and durable evidence into this
  canonical file; do not create `a`/`b` variants, sidecars, or combined
  multi-task work orders. For that task, this file wins.
- `docs/CONTRACT.md`: frozen cross-track interfaces.
- `docs/README.md`: documentation index and retention rules.
- `docs/team-workflow.md`: how the humans, chats, and Claude Code loop works.
- `data/manifest.json`: canonical record of anchor regulations (with versions
  and effective dates) and codebase roles (with pinned commits). Any doc or code
  referencing a corpus commit or regulation version must agree with it.
- `CLAUDE.md`: this file, with conventions, pins, and locked decisions.

**Precedence for a given task: work order > CLAUDE.md.** The signed
`docs/CONTRACT.md` separately governs cross-track interfaces. If these records
conflict, STOP and report the conflict—do not silently pick one. A task without
its canonical work order is not executable; create or request that work order
instead of falling back to another document.

## How you (Claude Code) are used here

You are always invoked as: _"Read CLAUDE.md and
`docs/tasks/T<n>.<n>-work-order.md`. Execute."_ The work order carries current
state, accepted amendments, and durable evidence—trust it over chat memory.
Standing expectations:

- Write the gate test **first**; the task is done only when it and all prior
  gates pass.
- Work on the owning permanent branch `track-<a|b|c>`; commit prefix
  `T<n>.<n>: <what changed>`.
- **Update `STATUS.md` in the same commit as the work**: set the task's line
  (state, artifact path) as part of completing it. The ledger must never lag the
  artifacts — a state change without its STATUS line is an incomplete commit.
- Leave `# DECISION:` comments where you resolved an ambiguity; list them in
  your final summary (they get reviewed in the track chat).
- Hit a contract question (anything touching `schemas.py`, `tools.py`
  signatures, `docs/CONTRACT.md`)? **Stop and ask** — that is a CONTRACT CHANGE,
  decided in chat, not here.

## Locked technical decisions — do not re-litigate

1. **AST backend:** tree-sitter, grammar `yutaro-sakamoto/tree-sitter-cobol`,
   **vendored** at `vendor/tree-sitter-cobol/`, **pinned to
   `e99dbdc3d800d5fa2796476efd60af91f6b43d93`**. No grammar upgrades without
   re-running the T1.1 validation gate.
2. **Mandatory preprocessor** before any parse (line-count-preserving): mask
   `EXEC CICS/SQL/DLI … END-EXEC` (preserving the sentence-terminating period
   when `END-EXEC.` closed a sentence) and handle `COPY … REPLACING`. Lives in
   `src/cobol_archaeologist/ingest/cleaner.py`. Not a workaround — a pipeline
   stage; raw CardDemo CICS code is unparseable by every backend without it.
3. **GnuCOBOL `cobc` (3.1.2) is the compile/behavior oracle only** — never the
   parser. Only batch `CB*` programs compile; CICS programs failing under it is
   expected, not an error. **Generalized (T2.4 corrective pass, BL-16): local harnesses
   generate hypotheses; only the real toolchain closes gates.** A pure-text
   probe harness once reproduced a build's gate number exactly, was trusted
   through six iterations of changes to the code it modelled, and diverged
   (0.5457 vs the build's 0.6537) — because it had no validation step and so
   could not model rejected mutations changing the sample. Validating an
   instrument once and trusting it after changing its subject is the defect. A
   gate's number of record comes from the run that owns it.
4. **Line-number fidelity is sacred:** every public return that mentions a line
   refers to the **original source file**; all transformations carry a line-map.
   Benchmark labels are line-level; breaking this breaks the benchmark.
5. **Corpora:** AWS CardDemo (Apache 2.0, pin `59cc6c2fd7eb`) = anchor; IBM CICS
   CBSA (EPL 2.0) = secondary. Fetched by `scripts/fetch_corpora.sh` into
   `data/corpora/` — never vendored into the repo. Pins and roles are recorded
   canonically in `data/manifest.json`.
6. **Anchor regulations (T0.1 + T0.2 fit decision; RE-ANCHORED 2026-07-09 at
   T2.1, user-approved — ratified in Track B chat 2026-07-09):** primary clause set = **RBI
   (Commercial Banks – Credit Cards and Debit Cards: Issuance and Conduct)
   Directions, 2025** (effective 2025-11-28) **plus the KYC/AML clauses its
   paragraph 90 incorporates by reference**; the **RBI KYC Directions, 2025**
   anchor the real-curated seed (T2.5) and the T6 versioned-judgment pairs.
   **History (T2.1 re-verification):** the original 2022 Master Direction
   (effective 2022-07-01, amended 2024-03-07) was **repealed for commercial
   banks on 2025-11-28** and reissued as this 2025 instrument — values carried
   over unchanged, clauses renumbered into paragraphs 1–97. The repealed 2022 MD
   supplies T6 old sides (2022 vs 2024 vs 2025) and the 2022→2025 supersession
   pair; its numbering (the KYC bridge was clause 29, not 20 — para 20 was
   co-branding outsourcing) is preserved as `check.prior_2022` in `clauses.jsonl`.
   2025 paragraph numbers were primary-confirmed against the archived PDF during
   T2.5 Phase 2 with zero corrections. Pure-KYC logic with no CardDemo host will
   live in the planned GnuCOBOL-native runnable base. Taxonomy v1 with per-class CardDemo loci:
   `docs/tasks/T0.2-work-order.md`.
7. **Integrity rules (benchmark):** MO-0 benign edits + style diversification
   mandatory; verification tiered (1 executed / 2 static / 3 entailment-only,
   tier recorded per finding); LLM judges/verifiers must be a different model
   family than the system under test.

## Layout (target) and ownership

- `src/cobol_archaeologist/ingest/cleaner.py`: preprocessor (A, T1.1).
- `src/cobol_archaeologist/parser/`: AST spans and copybooks (A, T1.1).
- `src/cobol_archaeologist/static_analysis/`: graph, dataflow, slicer (A,
  T1.2-T1.4).
- `src/cobol_archaeologist/model/run_cobol.py`: GnuCOBOL harness (A, T1.5).
- `src/cobol_archaeologist/tools.py`: agent tool facade (A, T1.6).
- `src/cobol_archaeologist/schemas.py`: pydantic models (C, T0.3).
- `src/cobol_archaeologist/benchmark/`: mutation ops and build CLI (B,
  T2.2-T2.6).
- `src/cobol_archaeologist/rag/`: loader, chunker, index, embedder (C,
  T3.1-T3.3).
- `src/cobol_archaeologist/model/{prompt,verify}.py`: policy and verification
  (C, T3.4, T3.6).
- `src/cobol_archaeologist/agent/`: loop and stub tool layer (C, T3.5).
- `src/cobol_archaeologist/eval/`: metrics and runs (C, T4.x).
- `vendor/tree-sitter-cobol/`: pinned grammar. Never edit.
- `tests/`: pytest, with golden fixtures in `tests/fixtures/`.
- `scripts/fetch_corpora.sh`: corpus fetcher.
- `data/manifest.json`: anchor manifest (B, T0.1). `data/regulations/`,
  `data/benchmark/`: clause records and generated instances (B, T2.x).

**Ownership = write access** (A/B/C above). Never edit another track's modules.
If their code blocks you, report it; the owning track fixes it. `STATUS.md` is
the one file every track writes — but only its own tasks' lines.

## Conventions

- Python 3.12 · `pydantic>=2` for all inter-module shapes · `pytest`.
- Every tool in `tools.py` returns **structured data + source pointers, never
  raw dumps**. Code text is capped at about 60 lines with a pointer to fetch
  more.
- `tree_sitter==0.21.3` pinned; changing bindings is a deliberate migration.
- Keep the regex fallback path alive wherever a work order says so.

## Commands

```bash
pip install -e ".[dev]"
bash scripts/fetch_corpora.sh
pytest tests/ -x -q
```
