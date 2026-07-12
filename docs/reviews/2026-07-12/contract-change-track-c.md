# CONTRACT CHANGE proposal → Track C chat (schema owner)

**From:** Track B (via 2026-07-12 external review) · **Re:** `schemas.py`
(SCHEMA FREEZE) + `docs/CONTRACT.md` · **Status:** proposal, needs Track C
sign-off before T2.2 / T2.5-Phase-3 emit any interprocedural instances.

Two items. **Item 1 is a true contract change; Item 2 may not need one.** Do not
edit `schemas.py` until this is ratified in chat.

---

## Item 1 (F2) — the schema cannot bind an interprocedural finding's line to its program

### Problem
Today (`src/cobol_archaeologist/schemas.py`):

```python
class CodeLocus(BaseModel):        # :53
    programs: list[str] = Field(min_length=1)
    paragraphs: list[str]
    line_span: tuple[int, int]     # ← ONE span for the whole locus
    slice_vars: list[str]
    is_interprocedural: bool

class Labels(BaseModel):           # :75
    program_level: Literal["drift", "conformant"]
    paragraph_level: Literal["drift", "conformant"]
    line_level: list[int]          # ← bare ints, no program/file
```

For a finding spanning two programs (an **MO-3× / MO-6×** interprocedural
mutation), there is no way to say *which* paragraph/line lives in *which*
program: `programs=[A,B]`, `paragraphs=[p,q,r]`, one `line_span`, and
`line_level=[120, 340]` with no binding. That directly threatens the
**headline interprocedural-localization metric** (`CONTRACT.md` §stratification,
~L77: `code_locus.is_interprocedural`; headline claim ~L139–146).

### Proposed shape

```python
class SourceLocus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program: str
    paragraph: str | None = None
    line_span: tuple[int, int]     # keeps the existing 1-based ordered validator

class CodeLocus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loci: list[SourceLocus] = Field(min_length=1)   # one per program touched
    slice_vars: list[str]
    is_interprocedural: bool        # keep as the deliberate stratification key
```
and label lines as `(program, line)` pairs:
```python
    line_level: list[SourceLineRef]   # SourceLineRef{program: str, line: int}
```

### Decisions for the chat
1. **Adopt `SourceLocus`/`loci`**, or keep the flat fields and *add* per-program
   line binding some other way?
2. **Backward compatibility:** single-program instances are the common case —
   full replace, or a compat shim (derive `programs`/`paragraphs`/`line_span`
   as properties)? A full replace is cleaner but rewrites the D1 fixture.
3. `SourceLocus.paragraph` optional vs required?
4. Add `file`/`copybook` to `SourceLocus` now, or defer?

### Blast radius (who rewrites what)
- **C:** `schemas.py`, `tests/test_schemas.py`, `docs/CONTRACT.md`, the
  `tests/fixtures/drift_instance_d1_kyc.json` fixture, T4.2 metric code.
- **B:** T2.5 seed emitter + T2.2 mutation emitter (not yet written — cheapest
  moment to change is now).
- **A:** none (consumes, doesn't emit DriftInstances).

---

## Item 2 (F1c) — `current_value` has no common comparator

### Problem
`CurrentValue` is `{kind: str, value: Any}` with `extra="forbid"`. The T2.1
convention puts the comparator **inside** `value`
(`{"amount": 3, "comparator": "strictly_greater"}`) for some records and a bare
scalar for others. Generic MO-1/MO-5 targeting and D5 (`>` vs `>=`) scoring then
need record-shape-specific code — friction against "targeting map is data."

### Key nuance
`value: Any` **already permits** the in-value comparator with **no schema
change**. A *top-level* `comparator` field **would** be a contract change
(`extra="forbid"`). So this is a convention call, not necessarily a freeze break:

- **Option A (no contract change):** keep comparator-in-`value`; publish one
  canonical accessor helper (`comparator_of(cv) -> str|None`) both B and C use,
  and require D1/D5 records to carry it. Recommended.
- **Option B (contract change):** hoist `comparator: Comparator | None` to a
  frozen top-level field on `CurrentValue`. Only if T4.2 D5 scoring proves
  Option A too fragile.

**Ask:** ratify Item 1's shape (or an alternative) and pick A/B for Item 2 in
the Track C chat; Track C then makes the edits and re-freezes.
