# FLAGS — cross-track message ledger

Append-only inbox per track. Rules:

1. A flag rides the commit of the deliverable that caused it (same-commit rule,
   like STATUS lines).
2. Format: `→ Track X | from Y | YYYY-MM-DD | T-n.n | message`.
3. The receiving track deletes its own entries once acknowledged in its chat
   (each track edits only its own inbox).
4. Session-start protocol includes reading this file alongside STATUS.md.
5. Urgent mid-session CONTRACT CHANGEs still get relayed directly in chat; this
   file is the async path, not the emergency path.

## Track A inbox

→ Track A | from C | 2026-07-07 | T0.4 | CONTRACT.md v1.1 reproduces your
committed ToolLayer Protocol verbatim. Two deltas beyond your A1/A2 flag were
picked up from tool_types.py and folded in as part of A1: run_cobol inputs typed
`RunInputs | None`, search_regulations returns `list[RegSearchHit]`. If either
was unintentional, raise a CONTRACT CHANGE.

→ Track A | from B | 2026-07-12 | T1.0/T1.1/T1.3 | External review — 3 code bugs
(no decision needed): (F5) qualified-name trace not case-insensitive —
`dataflow.py:374` splits uppercase " OF "/" IN " then uppercases, so
`errmsgo of cosgn0ao` → 0 sites vs 2 uppercase; normalize spec to upper BEFORE
splitting. (F6) preprocessor drops unterminated EXEC…END-EXEC / COPY…REPLACING
at EOF (masked output, 0 masked_spans, no error) — raise a structured error;
line-fidelity invariant. (F10) fetch_corpora.sh skips CardDemo when the dir
exists without checking HEAD == 59cc6c2. Full detail + the F7 entry_points/D6
design call: docs/reviews/2026-07-12/chat-track-a.md.

→ Track A | from C | 2026-07-12 | CONTRACT CHANGE | schemas.py v2 (loci,
recursive CurrentValue, target_path). No action: A consumes DriftInstances and
does not emit them; tool_types.py is untouched. FYI only.

## Track B inbox

→ Track B | from A | 2026-07-13 | T1.6 | `get_data_layout` live — D4 mutation
targeting can use field trees + original-source VALUE text. Two things to know:
(1) VALUE literals are NOT inline on `FieldLayout` (the frozen shape is name /
level / pic / redefines / children). `DataLayout.source` spans the record's whole
declaration in ORIGINAL coordinates — read the literal from there. Do NOT read a
VALUE out of preprocessed text: the continued-literal splice rewrites it to
`VALUE 'X'` and would corrupt your D4 evidence (docs/tool-semantics.md §3). If you
want the literal inline on FieldLayout, say so — it is a CONTRACT CHANGE and the
wiring already has the data. (2) For a copybook-declared record, `source.program`
is the COPYBOOK STEM (e.g. `CVACT01Y`), not a program id. Also: F5/F6/F10 from the
2026-07-12 review are fixed.

→ Track B | from A | 2026-07-12 | T1.4 | T1.4 done. T2.2 now waits only on T1.5.

→ Track B | from A | 2026-07-12 | T1.5 | T1.5 done — `compile_check` + `run_cobol`
live at `model/run_cobol.py`. T2.2 fully unblocked. `CompileResult` is a module
type (import from `model.run_cobol`, NOT tool_types). `compile_check(source)`
takes self-contained source: expand copybooks (T1.1 `copybooks.expand`) before
calling it — its signature has no copybook path. Harness self-configures cobc
(discovers `COBC`/PATH, derives config dir); tests skip cleanly where cobc is
absent.

→ Track B | from C | 2026-07-12 | CONTRACT CHANGE RATIFIED | schemas.py is v2.
Item 1 (loci/SourceLineRef) and Item 3 (target_path) adopted; Item 2 resolved
as Option C, NOT A or B — current_value is recursive, so comparator is a typed
field on every node, not a top-level hoist. Reasoning + full blast radius:
docs/reviews/2026-07-12/contract-change-track-c-RESOLVED.md.
YOUR MIGRATION: ~10 current_value blocks in clauses.jsonl move comparator out
of `value` into the typed `comparator` field (CC-10a's "fortnight" → `note`).
tests/test_clauses.py goes red until you do — that is the intended signal.
T2.2 / T2.5-Phase-3 emitters must target v2: `loci` (not programs/paragraphs/
line_span), `line_level` as SourceLineRefs, and `target_path` REQUIRED for
D1/D5 against composite clauses (7 of your 19). T6 byte-identical-code_locus
obligation carries over unchanged.

## Track C inbox

→ Track C | from A | 2026-07-13 | T1.6 | T1.6 done. `RealToolLayer`
(`src/cobol_archaeologist/tools.py`) is constructor-swappable for your stub —
`isinstance(layer, ToolLayer)` is asserted in `tests/test_tools.py`. **Read
`docs/tool-semantics.md` before the seam test**: it enumerates the sentinel
semantics your stub must reproduce, not just the types (`<preamble>` synthetic
paragraph; `NodeRef.paragraph=""` = external program entry; `ref.program` may be a
COPYBOOK STEM, not a program you can `read_program()`; `"?ambiguous"` statement_kind;
`REDEFINES-alias` marker sites; 88→parent mapping; truncated/refetch convention;
CICS `compiled_ok=False` = Tier-1 unavailable, NOT an error). A stub with valid
shapes but different sentinel meanings passes `isinstance` and still fails at the
seam. `search_regulations` still raises `NotImplementedError` — yours.

→ Track C | from B | 2026-07-15 | T2.5 | Real-curated seed is available at
`data/benchmark/seed/real_curated.jsonl` for T4.2 pairing logic: 21 instances and
5 verdict-flipping T6 pairs (P1 at two loci, plus P3/P4/P5). Zero degraded pairs;
P2 was retired on primary evidence and P6 remains a citation-axis probe rather
than a verdict-flipping pair.
