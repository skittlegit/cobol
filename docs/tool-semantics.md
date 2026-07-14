# Tool semantics — what a ToolLayer consumer must know (T1.6)

Companion to `docs/CONTRACT.md` Part 1 and `src/cobol_archaeologist/tool_types.py`
(normative). The contract fixes the **shapes**; this file fixes the **meanings** —
the sentinels, conventions, and edges that accumulated across the T1.1–T1.5
reviews and that a consumer cannot infer from the pydantic models alone.

**Read this before wiring an agent (or the Week-7 seam test) to `RealToolLayer`.**
`StubToolLayer` must reproduce these semantics, not just these types: a stub that
returns structurally valid models with different sentinel meanings will pass
`isinstance` and still fail at the seam.

Implementation: `src/cobol_archaeologist/tools.py`. Gate: `tests/test_tools.py`.

---

## 1. Sentinels

### `<preamble>` — the synthetic paragraph

Batch programs put their main driver code directly under `PROCEDURE DIVISION`,
**before the first paragraph header**. That unnamed region holds the root
`PERFORM` edges, so it is surfaced as one synthetic leading paragraph named
`<preamble>`.

- It is a **first-class node**: `read_paragraph(prog, "<preamble>")` works, and it
  appears in `callers`/`callees`, `VariableTrace.sites[*].ref.paragraph`, and
  `Slice.paragraphs`.
- Angle brackets are illegal in COBOL names, so it never collides with a real one.
- CICS programs generally have no preamble (their driver *is* a paragraph).
- Do not filter it out — for a batch program it is usually the top of the call tree
  (e.g. `CBACT04C.<preamble>` is the sole caller of `1050-UPDATE-ACCOUNT`).

### `NodeRef.paragraph == ""` — an external program entry

A cross-program `CALL 'X'` / CICS `LINK` / `XCTL` to a program **outside the parsed
set** still produces a real edge. Its target is `NodeRef(program="X", paragraph="")`,
meaning *"program entry; first paragraph unknown because X was not parsed"*.

The edge is never dropped — we know the target program even when we have not loaded
its paragraphs. An empty `paragraph` is therefore **not** a bug and not a missing
value; treat it as "entry point, unresolved". `find_callers("X", "")` is a legal,
meaningful query.

### `ref.program` may be a **copybook stem**, not a program id

`SourceRef` has a `program` field, not a `file` field. A declaration that physically
lives in a copybook records the **copybook's stem** there:

```
DataLayout(record="ACCOUNT-RECORD").source.program == "CVACT01Y"   # the copybook
```

This is what keeps every ref genuinely original-source (CLAUDE.md rule 4). It shows
up in `VariableTrace` declaration sites (`VALUE-clause`, `REDEFINES-alias`),
`Slice` VALUE-clause statements, `DataLayout.source`, and copybook `grep` hits.

**A consumer must not assume `ref.program` names a program it can `read_program()`.**
If it is not in the corpus, it is a copybook — reach it with `resolve_copybook(stem)`.

### `statement_kind` suffix `"?ambiguous"`

A bare name declared in several records of one program cannot be resolved to a single
field. Rather than guess, `trace_variable` returns **all** candidate sites with
`statement_kind` suffixed `"?ambiguous"` (e.g. `"MOVE?ambiguous"`).

- Ambiguity is **conservative, never silent**: sites are added, not dropped, and
  slices include them.
- To disambiguate, qualify the name: `trace_variable("ERRMSGO OF COSGN0AO")`.
- Name matching is **case-insensitive**, qualifier keyword included: `errmsgo of
  cosgn0ao` and `ERRMSGO OF COSGN0AO` return identical sites.

### `statement_kind == "REDEFINES-alias"`

When the traced field's storage overlaps a `REDEFINES` declaration, one **def site**
is emitted at the *redefining declaration* with this marker. It flags *"another name
addresses this storage"* — it is **not** a write through that alias. Full alias
analysis (writes through the alias flowing to the traced field) is out of scope; see
§4.

### 88-level condition names map to their parent field

An 88 is a condition name over the field above it, so:

- Tracing an 88 (`ERR-FLG-ON`) returns exactly the sites of its **parent**
  (`WS-ERR-FLG`) — the two traces are equal.
- `IF NOT ERR-FLG-ON` is a **use** of the parent; `SET ERR-FLG-OFF TO TRUE` is a
  **def** of the parent.
- In `DataLayout`, an 88 is a `FieldLayout` **child of the field it qualifies**
  (never of the record root), with `level=88` and `pic=None`.

---

## 2. Caps, truncation, and refetching

Every tool returns summaries + pointers, never a raw dump.

| Return | Cap | Flag |
|---|---|---|
| `ParagraphView.code` | `CODE_CAP_LINES` (60) | `truncated` |
| `CopybookExpansion.text` | `CODE_CAP_LINES` (60) | `truncated` |
| `GrepResult.matches` | `GREP_CAP_MATCHES` (200) | `truncated` |

**The convention:** when `truncated=True`, the accompanying `ref` still spans the
**whole** object, not the truncated excerpt. A 451-line paragraph returns 60 lines of
code with `ref.line_start=2986, ref.line_end=3436` — the pointer is what you refetch
from (narrow the range and call again, or read the file at those lines).

`ProgramView` carries paragraph **names and spans only**, by design — it is the index
you use to choose what to `read_paragraph`.

---

## 3. Per-tool notes

**`read_paragraph` / `read_program`** — code text comes from the **original** source
file, never the preprocessed buffer.

**`find_callers` / `find_callees`** — `NodeRef` passthrough over the call graph. An
unknown *program* raises `ToolLookupError`; an unknown *paragraph* returns `[]`, the
same as a genuine leaf. Cross-program reachability is **not** traversed: within a
program the only flow between paragraphs is `PERFORM`/`GO TO`, and cross-program
entry happens through the callee's own entry points.

**`trace_variable` / `slice_on`** — `program=None` is corpus-wide (union over every
program declaring the field); `program=<id>` scopes to one (contract amendment A2). A
named scope that does not exist raises rather than returning an empty trace.

**`resolve_copybook`** — every `LineMapEntry.source_file` names a **real file**. (The
underlying expander marks a caller's own lines with `""`, meaning "you know your own
path"; through the facade the consumer does not, so the facade rewrites `""` to the
copybook's path.)

**`get_data_layout`** — the record's field tree (name, level, PIC, REDEFINES,
children). `pic` is the picture string itself (`"S9(10)V99"`), not the clause
(`"PIC S9(10)V99"`); `level` is an int (`1`, not `"01"`).

`source` spans the record's **whole declaration** — the 01 line through its last
subordinate — in original coordinates. That span is how you get declaration **text**:

> ⚠️ **VALUE literals must be read from the ORIGINAL source, via `source`/the
> LineMap — never from a preprocessed buffer.** The preprocessor's continued-literal
> splice rewrites a `VALUE` continued across a line (col-7 `-`) into a placeholder
> (`VALUE 'X'`) so the grammar can scan it. That is fine for *structure* — which is
> why the field tree is built from that buffer, and why fields declared after a
> continued literal survive at all — but reading a VALUE **out** of it would silently
> corrupt D4 (stale reference data) evidence. See `docs/preprocessor-notes.md`.

The search is corpus-wide in sorted program order, first declarer wins. For a
copybook-declared record this is host-independent: whichever program COPYs it, the
answer resolves to the same original copybook coordinates.

**`grep`** — regex (case-insensitive) over **original** sources: programs **and
copybooks**. Copybooks are included deliberately — record layouts and their VALUE
literals (the D4 evidence) live there — and a copybook hit reports its **stem** as
`program`, per the convention above.

**`run_cobol`** — a full program (one with an `IDENTIFICATION`/`ID DIVISION`) passes
through unchanged; a bare snippet of procedure statements is wrapped in a minimal
batch shell. **The shell declares no storage**: anything needing `WORKING-STORAGE`
must be passed as a full program (wrapping one would mean inventing declarations the
caller never wrote).

> **`compiled_ok=False` is an answer, not an error.** GnuCOBOL is the compile/behavior
> oracle, never the parser (CLAUDE.md decision 3). CICS programs do not compile under
> it — that is **expected**, and means *"Tier-1 (executed) verification unavailable
> for this locus; fall back to Tier 2/3"*. It is never an exception. A **missing
> `cobc` binary**, by contrast, *does* raise `RuntimeError` — that is a broken
> environment, not a fact about the code.

**`search_regulations`** — raises `NotImplementedError`. The signature ships so the
contract is complete; **Track C owns the implementation** (T3.1–T3.3).

---

## 4. Documented limitations (inherited, not bugs)

These are known and deliberate. Do not design around them silently — if one blocks a
task, raise it rather than working around it locally.

- **LINKAGE / COMMAREA value flow is not modeled.** A corpus-wide trace unions
  per-program sites **by field name**; it does not thread a value across a
  `CALL`/`LINK`/`XCTL` boundary. Interprocedural *control* flow is modeled;
  interprocedural *data* flow through parameters is not.
- **Subscripts and reference modification are not tracked.** `X(I:L)` traces as `X`;
  the index/length identifiers are not emitted as their own sites.
- **`STRING`/`UNSTRING` source operands** are not uses (only the `INTO` targets are
  defs), per the normative def/use table.
- **Computed `GO TO … DEPENDING ON`** would need a multi-target statement shape. It
  does not occur in CardDemo (verified corpus-wide) and is not built.
- **CICS pseudo-conversational edges** (`RETURN TRANSID` / `START TRANSID`) are not
  call-graph edges — they transfer control through the CICS transaction table, and
  resolving them needs the transaction→program map.
- **`entry_points` currently returns forest roots**, i.e. *every* paragraph with no
  incoming `PERFORM`/`GO TO`. An isolated dead paragraph is therefore counted as an
  entry (and so as reachable). This is unsuitable as the basis for **D6 (dead
  compliance code)** detection and is **pending the F7 / D6 split** of "true program
  entry roots" from "forest roots" (review 2026-07-12; owner Track A). Do not build
  D6 reachability on `entry_points` until that lands.
- **Copybook nesting is capped at one level.** A `COPY` inside an already-included
  copybook is left as literal text rather than resolved (no CardDemo program
  exercises deeper nesting).

---

## 5. Errors

`ToolLookupError` (a `KeyError`) — an unknown program, paragraph, copybook, or
record. The contract's return models describe *answers*, not *failures*, and have no
error variant, so a name that does not exist raises rather than returning a hollow
model the agent would misread as "no results".
