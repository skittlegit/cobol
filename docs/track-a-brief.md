# Track A — Phase 1 Execution Brief (T1.1–T1.6)

Self-contained spec for implementing the program-analysis core. Milestone: **M1
— Slicing Validated** (`slice_on(var)` returns correct cross-paragraph slices on
hand-checked examples). Execute tasks in order; T1.5 can run parallel to
T1.2–T1.4. Every task ends with its gate test green and a commit prefixed with
the task ID.

Context you can rely on: `docs/tasks/T0.5-ast-decision-note.md` (why
tree-sitter; empirical evidence), `CLAUDE.md` (locked decisions, layout, pins).
The validated prototype is `src/cobol/spike_parser.py` — treat it as reference
logic to be dissolved, then delete it.

---

## T1.0 (scaffolding, not in the playbook — do first, ~half day)

The repo is empty except the spike. Create:

- `pyproject.toml` — package `cobol_archaeologist`, deps: `tree_sitter==0.21.3`,
  `pydantic>=2`, dev deps `pytest`, `ruff`.
- The package skeleton per CLAUDE.md layout, with empty modules + docstrings.
- `vendor/tree-sitter-cobol/` — vendor grammar commit
  `e99dbdc3d800d5fa2796476efd60af91f6b43d93` (the `src/` dir with `parser.c`,
  `scanner.c`, `grammar.json`, `node-types.json` is sufficient; record the
  commit hash in `vendor/tree-sitter-cobol/PINNED`).
- `scripts/fetch_corpora.sh` — shallow-clone CardDemo at `59cc6c2fd7eb` into
  `data/corpora/carddemo/`; CBSA
  (`cicsdev/cics-banking-sample-application-cbsa`) at a commit you record the
  same way. `data/` is gitignored.
- `src/cobol_archaeologist/parser/_grammar.py` — build/load the tree-sitter
  language from `vendor/`, caching the compiled `.so` under `build/`
  (gitignored). Single accessor `get_language() -> Language`.

**Done when:** `pip install -e .` works; `pytest` collects; and this succeeds
after `fetch_corpora.sh`:

```bash
python -c "from cobol_archaeologist.parser._grammar import get_language; get_language()"
```

---

## T1.1 — Preprocessor + AST-backed parser

### 1a. Preprocessor — `ingest/cleaner.py`

Function `preprocess(source: str) -> PreprocessResult` where the result carries
`text` (same line count as input — invariant, assert it), and
`masked_spans: list[MaskedSpan]` with `kind`
(`exec_cics|exec_sql|exec_dli|copy_replacing`), `start_line`, `end_line`,
`original_text`. Rules (port from the spike, they are validated):

- `EXEC CICS|SQL|DLI … END-EXEC` → first line becomes `CONTINUE`, interior lines
  blank; **if the `END-EXEC` line ends with `.`, emit `CONTINUE.`** — this
  period is load-bearing (it was the difference between 1 and 60 paragraphs on
  COACTUPC).
- Comment lines (col 7 `*` or `/`) are never scanned for `EXEC`/`COPY`.
- `COPY … REPLACING` in the procedure division → masked the same way **for
  now**; the masked span is retained so 1c can expand it properly.

### 1b. Parser — `parser/paragraphs.py`

`parse_program(path) -> Program` (pydantic): program-id, divisions, and
`paragraphs: list[Paragraph]` with `name`, `start_line`, `end_line`,
`statements` (typed: IF/EVALUATE/PERFORM/MOVE/COMPUTE/other, with nesting).
Grammar facts you need (from the spike): there is **no `paragraph` container
node** — compute spans as paragraph_header → next header/section/division end.
Control flow appears as `if_header`/`else_header`/`END_IF`,
`evaluate_header`/`when`/`END_EVALUATE`; PERFORM call targets are
`perform_procedure` nodes under `perform_statement_call_proc`; loops are
`perform_statement_loop`. Keep a **regex fallback**
(`parse_program(..., backend="regex")`) producing the same `Program` shape with
`statements=[]` — downstream must never hard-block on the AST.

### 1c. Copybook expansion — `parser/copybooks.py`

Real expansion replacing the spike's masking: resolve `COPY X` /
`COPY X REPLACING ==a== BY ==b==` against a copybook search path (CardDemo:
`app/cpy/`, `app/cpy-bms/`), apply pseudo-text replacement, and return expanded
text **plus a `LineMap`** (expanded line → (file, original line)). All
downstream coordinates must round-trip through the LineMap; benchmark labels
(and MO-1×, the stale-threshold-in-copybook mutation) depend on it.

**Gate (playbook "done when"):** paragraphs + nesting correct on **10
hand-checked CardDemo programs**. Use: `CBTRN02C, CBACT01C, CBACT04C, CBSTM03A`
(batch) and `COSGN00C, COACTUPC, COACTVWC, COCRDUPC, COTRN02C, COUSR02C` (CICS).
Method: for each, a golden fixture `tests/fixtures/paragraphs/<prog>.json`
(name, start, end per paragraph) built by regex extraction and **eyeballed once
against the source**; test asserts exact match + zero ERROR nodes after
preprocessing + at least one correctly-nested IF-within-IF and one EVALUATE
verified by hand in two of the programs.

---

## T1.2 — Call graph — `static_analysis/call_graph.py`

`build_call_graph(programs: list[Program]) -> CallGraph` with edges from:

- `PERFORM para` / `PERFORM a THRU b` (expand THRU over the paragraph order),
  `GO TO`;
- **EXEC side-channel (required):** the AST cannot see into masked EXEC blocks,
  so extract `EXEC CICS LINK PROGRAM(...)` / `XCTL PROGRAM(...)` edges by regex
  over `PreprocessResult.masked_spans.original_text` — the blocks are rigidly
  formatted; regex is adequate and this is the deliberate design, not a hack.
  Node identity: `(program_id, paragraph_name)`; cross-program edges from
  LINK/XCTL and `CALL`. API: `callers(node)`, `callees(node)`, reachability
  query (needed later by D6 dead-code logic).

**Gate:** `find_callers`/`find_callees` correct on CardDemo — golden fixtures
for 5 programs incl. one THRU chain and one LINK/XCTL edge, hand-verified.

## T1.3 — Interprocedural def-use — `static_analysis/dataflow.py`

`trace_variable(var, programs) -> VariableTrace` listing every def site
(MOVE/COMPUTE/ADD/… target, INITIALIZE, VALUE clause) and use site (conditions,
sources, arguments) across the call graph, each site = (program, paragraph,
line, kind). Resolve qualified names (`X OF GROUP`) and note REDEFINES aliases
(flag, don't fully alias-analyze — record the limitation in the module
docstring).

**Gate:** all read/write sites correct for **10 sample variables** across ≥3
programs, golden-fixture verified (include one copybook-defined field to
exercise the LineMap).

## T1.4 — Slicer — `static_analysis/slicer.py` ⛳ M1

`slice_on(var) -> Slice`: the cross-paragraph statements affecting `var` —
backward slice over def-use + control dependence (a statement's guarding
IF/EVALUATE conditions are in the slice). Output: ordered statements with
(program, paragraph, line) + the involved paragraphs; must be compact
(statements, not whole paragraphs).

**Gate (M1):** slices match **10 hand-built slices** exactly (fixtures; build
them from batch programs where behavior is checkable, e.g. `CBTRN02C`
transaction-validation variables).

## T1.5 — run_cobol harness — `model/run_cobol.py` (parallel to T1.2–T1.4)

`run_cobol(...) -> RunResult`

(full signature:
`run_cobol(source: str, stdin: str = "", files: dict[str, str] = {})`)

(compiled_ok, stdout, stderr, exit_code, timed_out): compile with
`cobc -x -std=ibm` in a temp dir, execute with a **5s timeout**, no network,
cwd-jailed. Also expose `compile_check(source) -> CompileResult`
(`-fsyntax-only`) — this is the oracle T2.2's mutation operators call. Document
loudly: CICS programs fail here **by design**; callers must treat non-compilable
as "Tier-1 verification unavailable", not as an error.

**Gate:** runs a trivial fixture program and one real batch slice end-to-end;
timeout test.

## T1.6 — Tool layer — `tools.py`

Facade over T1.1–T1.5 exposing exactly the contract below. Every return is a
pydantic model with **summaries + source pointers (program, paragraph, line
spans) — never full-file dumps**; any code text is capped (~60 lines) with a
pointer to fetch more.

- `read_paragraph(program, name)` returns code, span, and callers/callees
  summary.
- `read_program(program)` returns metadata and paragraph names/spans only.
- `find_callers(program, para)` returns `list[NodeRef]`.
- `find_callees(program, para)` returns `list[NodeRef]`.
- `trace_variable(var)` returns `VariableTrace`.
- `slice_on(var)` returns `Slice`.
- `resolve_copybook(name)` returns expanded text and a LineMap summary.
- `get_data_layout(record)` returns fields, PIC, and REDEFINES tree.
- `grep(pattern)` returns matches with `(program, line)`.
- `run_cobol(snippet, inputs)` returns `RunResult`.
- `search_regulations(query)` is a typed stub that raises `NotImplementedError`.
  Track C owns the implementation, but the signature ships now so the contract
  is complete.

**Gate:** every tool callable + unit-tested; a smoke script answers "which
paragraphs write `ACCT-CURR-BAL` and who calls them?" using only tool calls.

---

## Standing rules for the implementing agent

1. Never edit `vendor/`; grammar upgrades are a deliberate task with the T1.1
   gate re-run.
2. Line-number fidelity is sacred: every public return that mentions a line
   refers to the **original source file** via the LineMap. Add an invariant
   test.
3. Gates are written as tests **before** implementation; a task is done only
   when its gate passes and prior gates stay green.
4. If the grammar cannot represent something (ERROR nodes appear on a corpus
   program), do not patch the grammar — extend the preprocessor, record the
   pattern in `docs/preprocessor-notes.md`, and add the program to the
   regression fixtures.
5. Anything ambiguous in this brief: prefer the choice that keeps the tool
   contract stable, and leave a `# DECISION:` comment explaining it.
