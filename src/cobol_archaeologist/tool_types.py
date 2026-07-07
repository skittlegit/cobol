"""Tool I/O contract types (CONTRACT.md Part 1, normative form).

This module IS the tool contract: Track A's real tool layer (T1.6) and Track
C's ``StubToolLayer`` (agent/stub_tools.py) both implement :class:`ToolLayer`
and return exactly these models. Changing anything here is a CONTRACT CHANGE —
flag to Tracks A/B/C before merging.

Conventions bound by CONTRACT.md:
- Every line number refers to the ORIGINAL source file (via the preprocessor
  LineMap), never to preprocessed/expanded text.
- Code text in any return is capped at ``CODE_CAP_LINES``; ``truncated=True``
  plus the ``ref`` pointer tells the consumer where to fetch more.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from cobol_archaeologist.schemas import RegulationClause

CODE_CAP_LINES = 60


# --------------------------------------------------------------------------
# Pointer primitives
# --------------------------------------------------------------------------

class NodeRef(BaseModel):
    """Identity of a call-graph node: one paragraph in one program."""
    program: str
    paragraph: str


class SourceRef(BaseModel):
    """Pointer into original source. line_end is inclusive."""
    program: str
    paragraph: str | None = None
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


# --------------------------------------------------------------------------
# read_paragraph / read_program
# --------------------------------------------------------------------------

class ParagraphView(BaseModel):
    ref: SourceRef
    name: str
    code: str  # capped at CODE_CAP_LINES
    truncated: bool = False
    callers: list[NodeRef] = []
    callees: list[NodeRef] = []


class ParagraphSpan(BaseModel):
    name: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class ProgramView(BaseModel):
    program: str
    path: str
    paragraphs: list[ParagraphSpan]


# --------------------------------------------------------------------------
# trace_variable / slice_on
# --------------------------------------------------------------------------

class DefUseSite(BaseModel):
    kind: str = Field(pattern="^(def|use)$")
    ref: SourceRef
    statement_kind: str  # MOVE / COMPUTE / IF / VALUE-clause / ...
    excerpt: str = ""    # single statement, not a dump


class VariableTrace(BaseModel):
    variable: str
    scoped_program: str | None = None  # None = corpus-wide (CONTRACT amendment A2)
    sites: list[DefUseSite]


class SliceStatement(BaseModel):
    ref: SourceRef
    text: str


class Slice(BaseModel):
    variable: str
    scoped_program: str | None = None  # None = corpus-wide (CONTRACT amendment A2)
    statements: list[SliceStatement]   # ordered; statements, not whole paragraphs
    paragraphs: list[NodeRef]
    is_interprocedural: bool


# --------------------------------------------------------------------------
# resolve_copybook / get_data_layout
# --------------------------------------------------------------------------

class LineMapEntry(BaseModel):
    """Expanded-line range -> original (file, first line)."""
    expanded_start: int = Field(ge=1)
    expanded_end: int = Field(ge=1)
    source_file: str
    source_line_start: int = Field(ge=1)


class CopybookExpansion(BaseModel):
    name: str
    text: str  # capped at CODE_CAP_LINES
    truncated: bool = False
    line_map: list[LineMapEntry]


class FieldLayout(BaseModel):
    """One data item; recursive over group items."""
    name: str
    level: int
    pic: str | None = None
    redefines: str | None = None
    children: list["FieldLayout"] = []


class DataLayout(BaseModel):
    record: str
    root: FieldLayout
    source: SourceRef


# --------------------------------------------------------------------------
# grep / run_cobol / search_regulations
# --------------------------------------------------------------------------

class GrepMatch(BaseModel):
    program: str
    line: int = Field(ge=1)
    text: str


class GrepResult(BaseModel):
    pattern: str
    matches: list[GrepMatch]
    truncated: bool = False


class RunInputs(BaseModel):
    stdin: str = ""
    files: dict[str, str] = {}


class RunResult(BaseModel):
    compiled_ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False


class RegSearchHit(BaseModel):
    clause: RegulationClause
    score: float


# --------------------------------------------------------------------------
# The contract surface
# --------------------------------------------------------------------------

@runtime_checkable
class ToolLayer(Protocol):
    """Both Track A's real layer (tools.py, T1.6) and Track C's StubToolLayer
    implement exactly this. The Week-7 seam test is a constructor swap of one
    ToolLayer for another — nothing else may need to change."""

    def read_paragraph(self, program: str, name: str) -> ParagraphView: ...
    def read_program(self, program: str) -> ProgramView: ...
    def find_callers(self, program: str, para: str) -> list[NodeRef]: ...
    def find_callees(self, program: str, para: str) -> list[NodeRef]: ...
    def trace_variable(self, var: str, program: str | None = None) -> VariableTrace: ...
    def slice_on(self, var: str, program: str | None = None) -> Slice: ...
    def resolve_copybook(self, name: str) -> CopybookExpansion: ...
    def get_data_layout(self, record: str) -> DataLayout: ...
    def grep(self, pattern: str) -> GrepResult: ...
    def run_cobol(self, snippet: str, inputs: RunInputs | None = None) -> RunResult: ...
    def search_regulations(self, query: str) -> list[RegSearchHit]: ...
