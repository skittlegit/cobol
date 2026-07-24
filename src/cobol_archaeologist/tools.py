"""Agent tool facade over parser, static analysis, and harness (Track A, T1.6).

:class:`RealToolLayer` is the concrete implementation of the frozen
``tool_types.ToolLayer`` Protocol (CONTRACT.md Part 1). Track C's
``StubToolLayer`` implements the same Protocol, so the Week-7 seam test is a
one-line constructor swap — this class is isinstance-checked against the
Protocol in ``tests/test_tools.py``.

Every return is a pydantic model of summaries + source pointers, never a raw
dump: code text is capped at ``CODE_CAP_LINES`` and grep at
``GREP_CAP_MATCHES``, each with ``truncated=True`` plus a ref telling the
consumer where to fetch the rest. Every line number in every return refers to
the ORIGINAL source file (CLAUDE.md rule 4).

The sentinels and edge semantics a consumer must know are enumerated in
``docs/tasks/T1.6-work-order.md`` — read its consumer-semantics register before
wiring an agent to this.
"""

from __future__ import annotations

import re
from pathlib import Path

from cobol_archaeologist.ingest.cleaner import PreprocessResult, preprocess
from cobol_archaeologist.model import run_cobol as _harness
from cobol_archaeologist.parser._grammar import get_language
from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.parser.paragraphs import Program, parse_program
from cobol_archaeologist.static_analysis import dataflow as _dataflow
from cobol_archaeologist.static_analysis import slicer as _slicer
from cobol_archaeologist.static_analysis.call_graph import CallGraph, build_call_graph
from cobol_archaeologist.tool_types import (
    CODE_CAP_LINES,
    CopybookExpansion,
    DataLayout,
    FieldLayout,
    GrepMatch,
    GrepResult,
    LineMapEntry,
    NodeRef,
    ParagraphSpan,
    ParagraphView,
    ProgramView,
    RegSearchHit,
    RunInputs,
    RunResult,
    Slice,
    SourceRef,
    VariableTrace,
)

GREP_CAP_MATCHES = 200

_PROGRAM_EXTS = (".cbl", ".cob")
_COPYBOOK_EXTS = (".cpy", ".cbl")
_PROGRAM_ID_RE = re.compile(
    r"PROGRAM-ID\.\s+([A-Za-z0-9][A-Za-z0-9_-]*)", re.IGNORECASE
)
_ID_DIVISION_RE = re.compile(
    r"^\s*(IDENTIFICATION|ID)\s+DIVISION", re.IGNORECASE | re.MULTILINE
)
_PIC_PREFIX_RE = re.compile(r"^(PICTURE|PIC)\s+(IS\s+)?", re.IGNORECASE)

# Levels that terminate a record: another 01 (or lower), or a standalone 77.
_STANDALONE_LEVEL = 77
_CONDITION_LEVEL = 88

_SNIPPET_SHELL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SNIPPET.
       PROCEDURE DIVISION.
{body}
           STOP RUN.
"""


class ToolLookupError(KeyError):
    """An unknown program, paragraph, copybook, or record name.

    The contract's return models have no error variant (they describe answers,
    not failures), so a name that does not exist in the corpus raises rather
    than returning a hollow model the agent would read as "no results".
    """


# --------------------------------------------------------------------------
# Data-division model (backs get_data_layout)
# --------------------------------------------------------------------------


class _Decl:
    """One data_description, resolved to original-source coordinates."""

    __slots__ = (
        "level",
        "name",
        "pic",
        "redefines",
        "program",
        "line_start",
        "line_end",
    )

    def __init__(self, level, name, pic, redefines, program, line_start, line_end):
        self.level = level
        self.name = name
        self.pic = pic
        self.redefines = redefines
        self.program = program  # original file's stem (program id or copybook)
        self.line_start = line_start  # ORIGINAL source line
        self.line_end = line_end


def _clean_pic(text: str | None) -> str | None:
    """'PIC S9(10)V99' -> 'S9(10)V99' (the picture string itself, per the
    tool_types.FieldLayout gate: pic='9(11)', not 'PIC 9(11)')."""
    if text is None:
        return None
    return _PIC_PREFIX_RE.sub("", text.strip()).strip() or None


def _resolve_line(line_map: list[LineMapEntry], expanded_line: int) -> tuple[str, int]:
    for entry in line_map:
        if entry.expanded_start <= expanded_line <= entry.expanded_end:
            return entry.source_file, entry.source_line_start + (
                expanded_line - entry.expanded_start
            )
    return "", expanded_line


class RealToolLayer:
    """The real ToolLayer over a COBOL corpus.

    ``corpus_root`` is the directory holding the program sources (e.g.
    ``data/corpora/carddemo/app/cbl``), scanned non-recursively;
    ``copybook_paths`` are the COPY search dirs. ``regulations`` is accepted and
    held for Track C, which owns :meth:`search_regulations`.

    Programs are parsed on first touch and cached; the call graph is built once,
    over the whole corpus (cross-program CALL/LINK/XCTL edges need the full set)
    and cached.
    """

    def __init__(
        self,
        corpus_root: Path,
        copybook_paths: list[Path],
        regulations=None,
    ) -> None:
        self.corpus_root = Path(corpus_root)
        self.copybook_paths = [Path(p) for p in copybook_paths]
        self.regulations = regulations

        self._paths: dict[str, Path] = self._discover_programs()
        if not self._paths:
            raise ValueError(
                f"no COBOL program sources ({', '.join(_PROGRAM_EXTS)}) under {self.corpus_root} — "
                "corpus_root must be the directory holding the program sources"
            )

        self._programs: dict[str, Program] = {}
        self._sources: dict[str, list[str]] = {}
        self._decls: dict[str, list[_Decl]] = {}
        self._graph_cache: CallGraph | None = None

    # -- discovery + caches -------------------------------------------------

    def _discover_programs(self) -> dict[str, Path]:
        """program id -> path, by reading each source's PROGRAM-ID (cheap: no
        parse). Deterministic on collision: first path in sorted order wins."""
        found: dict[str, Path] = {}
        if not self.corpus_root.is_dir():
            return found
        for path in sorted(self.corpus_root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in _PROGRAM_EXTS:
                continue
            match = _PROGRAM_ID_RE.search(
                path.read_text(encoding="utf-8", errors="replace")
            )
            if match:
                found.setdefault(match.group(1).upper(), path)
        return found

    def _path(self, program: str) -> Path:
        try:
            return self._paths[program.upper()]
        except KeyError:
            raise ToolLookupError(
                f"unknown program {program!r} (corpus: {self.corpus_root})"
            ) from None

    def _program(self, program: str) -> Program:
        pid = program.upper()
        if pid not in self._programs:
            self._programs[pid] = parse_program(self._path(pid), include_preamble=True)
        return self._programs[pid]

    def _all_programs(self) -> list[Program]:
        return [self._program(pid) for pid in sorted(self._paths)]

    def _source_lines(self, program: str) -> list[str]:
        pid = program.upper()
        if pid not in self._sources:
            text = self._path(pid).read_text(encoding="utf-8", errors="replace")
            self._sources[pid] = text.splitlines()
        return self._sources[pid]

    def _graph(self) -> CallGraph:
        if self._graph_cache is None:
            programs = self._all_programs()
            pres: dict[str, PreprocessResult] = {
                p.program_id: preprocess(
                    self._path(p.program_id).read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
                for p in programs
            }
            self._graph_cache = build_call_graph(programs, pres)
        return self._graph_cache

    def _declarations(self, program: str) -> list[_Decl]:
        """Every data_description of ``program``, in declaration order, resolved
        to ORIGINAL source coordinates.

        Order matters: copybooks are expanded FIRST (so COPY-sourced records are
        visible and the LineMap can carry each line home), then the expanded text
        is preprocessed (line-count-preserving, so expanded line numbers survive
        and the parse reaches zero ERROR nodes). Structure is read from that
        buffer; text — VALUE literals above all — must NOT be, because the
        continued-literal splice rewrites them to a placeholder there
        (docs/tasks/T1.1-work-order.md). Callers read text from the original file
        via the returned line numbers.
        """
        from tree_sitter import Parser

        pid = program.upper()
        if pid in self._decls:
            return self._decls[pid]

        path = self._path(pid)
        exp = expand(
            path.read_text(encoding="utf-8", errors="replace"), self.copybook_paths
        )
        pre = preprocess(exp.text)
        parser = Parser()
        parser.set_language(get_language())
        tree = parser.parse(pre.text.encode())

        nodes: list = []

        def walk(node) -> None:
            if node.type == "data_description":
                nodes.append(node)
            for child in node.children:
                walk(child)

        walk(tree.root_node)

        decls: list[_Decl] = []
        for node in nodes:
            level_node = _child(node, "level_number")
            name_node = _child(node, "entry_name")
            if level_node is None or name_node is None:
                continue
            try:
                level = int(level_node.text.decode().strip())
            except ValueError:
                continue

            source_file, line_start = _resolve_line(
                exp.line_map, node.start_point[0] + 1
            )
            span = node.end_point[0] - node.start_point[0]
            # DECISION: a declaration physically in a copybook records its
            # ORIGINAL file's stem as `program` (e.g. "CVACT01Y"), matching the
            # convention T1.3 already established for decl SourceRefs — the
            # contract's SourceRef has a program field, not a file field.
            stem = Path(source_file).stem.upper() if source_file else pid
            decls.append(
                _Decl(
                    level=level,
                    name=name_node.text.decode(errors="replace").strip(),
                    pic=_clean_pic(_text(_child(node, "picture_clause"))),
                    redefines=_redefines_name(node),
                    program=stem,
                    line_start=line_start,
                    line_end=line_start + span,
                )
            )

        self._decls[pid] = decls
        return decls

    # -- ToolLayer: read_paragraph / read_program ---------------------------

    def read_paragraph(self, program: str, name: str) -> ParagraphView:
        prog = self._program(program)
        wanted = name.upper()
        para = next((p for p in prog.paragraphs if p.span.name.upper() == wanted), None)
        if para is None:
            raise ToolLookupError(f"unknown paragraph {name!r} in program {program!r}")

        span = para.span
        lines = self._source_lines(prog.program_id)[span.line_start - 1 : span.line_end]
        truncated = len(lines) > CODE_CAP_LINES
        code = "\n".join(ln.rstrip() for ln in lines[:CODE_CAP_LINES])

        node = NodeRef(program=prog.program_id, paragraph=span.name)
        graph = self._graph()
        return ParagraphView(
            # ref spans the WHOLE paragraph even when code is capped — it is the
            # pointer the consumer refetches from.
            ref=SourceRef(
                program=prog.program_id,
                paragraph=span.name,
                line_start=span.line_start,
                line_end=span.line_end,
            ),
            name=span.name,
            code=code,
            truncated=truncated,
            callers=graph.callers(node),
            callees=graph.callees(node),
        )

    def read_program(self, program: str) -> ProgramView:
        prog = self._program(program)
        return ProgramView(
            program=prog.program_id,
            path=str(self._path(prog.program_id)),
            paragraphs=[
                ParagraphSpan(
                    name=p.span.name,
                    line_start=p.span.line_start,
                    line_end=p.span.line_end,
                )
                for p in prog.paragraphs
            ],
        )

    # -- ToolLayer: call graph ----------------------------------------------

    def find_callers(self, program: str, para: str) -> list[NodeRef]:
        return self._graph().callers(self._node(program, para))

    def find_callees(self, program: str, para: str) -> list[NodeRef]:
        return self._graph().callees(self._node(program, para))

    def _node(self, program: str, para: str) -> NodeRef:
        """NodeRef passthrough, with a typo guard: the program must be one this
        corpus knows — either parsed, or named as the target of a cross-program
        CALL/LINK/XCTL (those carry paragraph="" — see the T1.6 work order).
        An unknown PARAGRAPH is not an error: it yields [] the same way a real
        leaf does."""
        pid = program.upper()
        if pid not in self._paths:
            graph = self._graph()
            known = {e.target.program for e in graph.edges} | set(
                graph.nodes_by_program
            )
            if pid not in known:
                raise ToolLookupError(
                    f"unknown program {program!r} (not in corpus, not a call target)"
                )
        return NodeRef(program=pid, paragraph=para)

    # -- ToolLayer: dataflow / slicing --------------------------------------

    def trace_variable(self, var: str, program: str | None = None) -> VariableTrace:
        scope = self._scope(program)
        return _dataflow.trace_variable(
            var, self._all_programs(), self._graph(), program=scope
        )

    def slice_on(self, var: str, program: str | None = None) -> Slice:
        scope = self._scope(program)
        return _slicer.slice_on(var, self._all_programs(), self._graph(), program=scope)

    def _scope(self, program: str | None) -> str | None:
        """A2 `program=` semantics: None = corpus-wide. A named scope must exist,
        or the caller would silently get an empty trace instead of an error."""
        if program is None:
            return None
        self._path(program)  # raises ToolLookupError if unknown
        return program.upper()

    # -- ToolLayer: copybooks / data layout ---------------------------------

    def resolve_copybook(self, name: str) -> CopybookExpansion:
        path = self._copybook_path(name)
        exp = expand(
            path.read_text(encoding="utf-8", errors="replace"), self.copybook_paths
        )
        lines = exp.text.splitlines()
        truncated = len(lines) > CODE_CAP_LINES

        # DECISION: copybooks.expand marks the caller's OWN lines with
        # source_file="" ("you already know your own path"). Through the facade
        # the consumer does NOT know it, so "" is rewritten to this copybook's
        # path — every LineMap entry a consumer sees names a real file.
        line_map = [
            LineMapEntry(
                expanded_start=e.expanded_start,
                expanded_end=e.expanded_end,
                source_file=e.source_file or str(path),
                source_line_start=e.source_line_start,
            )
            for e in exp.line_map
        ]
        return CopybookExpansion(
            name=path.stem.upper(),
            text="\n".join(ln.rstrip() for ln in lines[:CODE_CAP_LINES]),
            truncated=truncated,
            line_map=line_map,
        )

    def _copybook_path(self, name: str) -> Path:
        wanted = name.upper()
        for base in self.copybook_paths:
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if (
                    entry.is_file()
                    and entry.stem.upper() == wanted
                    and entry.suffix.lower() in _COPYBOOK_EXTS
                ):
                    return entry
        raise ToolLookupError(
            f"unknown copybook {name!r} (search: {self.copybook_paths})"
        )

    def get_data_layout(self, record: str) -> DataLayout:
        """The field tree of ``record`` (name, level, PIC, REDEFINES, children).

        Searched over the corpus in sorted program order; the first program that
        declares the record wins. That is deterministic AND host-independent for
        the common case: a record declared in a copybook resolves to the SAME
        original coordinates (the copybook's) whichever program COPYs it in.

        ``source`` spans the record's WHOLE declaration — the level-01 line
        through its last subordinate — in original coordinates, so a consumer
        reading those lines from the original file gets the true declaration
        text, VALUE literals included. Never read VALUE text from a preprocessed
        buffer (see :meth:`_declarations`).

        DECISION: the work order requires "VALUE text must be read from original
        source via LineMap, never preprocessed text", but ``FieldLayout`` has no
        ``value`` field and adding one is a CONTRACT CHANGE. Adding it was NOT
        assumed: the work order itself enumerates the field tree as exactly
        "(name, level, PIC, REDEFINES, children)" — i.e. FieldLayout as frozen.
        So the requirement is honoured as a PROVENANCE GUARANTEE on the pointer
        rather than as a new field: ``source`` spans the whole declaration in
        original coordinates, and reading it yields true VALUE text. If Track B
        (D4) would rather have the literal inline on FieldLayout, that is a
        CONTRACT CHANGE to raise in chat — the wiring here already has the data.
        """
        wanted = record.upper()
        for pid in sorted(self._paths):
            decls = self._declarations(pid)
            index = next(
                (i for i, d in enumerate(decls) if d.name.upper() == wanted), None
            )
            if index is None:
                continue
            return self._build_layout(decls, index)
        raise ToolLookupError(
            f"unknown record {record!r} (no program in the corpus declares it)"
        )

    def _build_layout(self, decls: list[_Decl], index: int) -> DataLayout:
        head = decls[index]
        root = FieldLayout(
            name=head.name,
            level=head.level,
            pic=head.pic,
            redefines=head.redefines,
        )

        stack: list[tuple[int, FieldLayout]] = [(head.level, root)]
        line_end = head.line_end

        for decl in decls[index + 1 :]:
            # A following 01 (or lower level), or a standalone 77, ends the record.
            if decl.level <= head.level or decl.level == _STANDALONE_LEVEL:
                break
            # A record is contiguous within one file; a declaration from another
            # file cannot be part of it (and must not stretch `source`).
            if decl.program != head.program:
                break

            field = FieldLayout(
                name=decl.name,
                level=decl.level,
                pic=decl.pic,
                redefines=decl.redefines,
            )
            if decl.level == _CONDITION_LEVEL:
                # An 88 condition-name qualifies the field above it and can have
                # no children of its own, so it is never pushed as a parent.
                stack[-1][1].children.append(field)
            else:
                while len(stack) > 1 and stack[-1][0] >= decl.level:
                    stack.pop()
                stack[-1][1].children.append(field)
                stack.append((decl.level, field))
            line_end = max(line_end, decl.line_end)

        return DataLayout(
            record=head.name,
            root=root,
            source=SourceRef(
                program=head.program,
                line_start=head.line_start,
                line_end=line_end,
            ),
        )

    # -- ToolLayer: grep ----------------------------------------------------

    def grep(self, pattern: str) -> GrepResult:
        """Regex over the ORIGINAL sources of the corpus.

        DECISION: copybooks are searched alongside programs. Record layouts and
        their VALUE literals — the D4 (stale reference data) evidence — live in
        copybooks, so a grep blind to them could not find the very constants the
        benchmark is about. A copybook hit reports its stem as ``program``, the
        same convention declaration SourceRefs already use (T1.3).
        """
        regex = re.compile(pattern, re.IGNORECASE)
        matches: list[GrepMatch] = []
        truncated = False

        for label, path in self._searchable_files():
            for lineno, text in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if regex.search(text):
                    if len(matches) >= GREP_CAP_MATCHES:
                        truncated = True
                        break
                    matches.append(
                        GrepMatch(program=label, line=lineno, text=text.rstrip())
                    )
            if truncated:
                break

        return GrepResult(pattern=pattern, matches=matches, truncated=truncated)

    def _searchable_files(self) -> list[tuple[str, Path]]:
        """(label, path) over programs then copybooks, in a stable order."""
        files: list[tuple[str, Path]] = [
            (pid, self._paths[pid]) for pid in sorted(self._paths)
        ]
        seen = {p.resolve() for _, p in files}
        for base in self.copybook_paths:
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if (
                    entry.is_file()
                    and entry.suffix.lower() in _COPYBOOK_EXTS
                    and entry.resolve() not in seen
                ):
                    seen.add(entry.resolve())
                    files.append((entry.stem.upper(), entry))
        return files

    # -- ToolLayer: run_cobol -----------------------------------------------

    def run_cobol(self, snippet: str, inputs: RunInputs | None = None) -> RunResult:
        """Compile and run ``snippet`` under the T1.5 GnuCOBOL harness.

        A full program (one with an IDENTIFICATION/ID DIVISION) passes through
        unchanged. A bare snippet — procedure-division statements — is wrapped
        in a minimal batch shell first. The shell declares NO storage: a snippet
        needing WORKING-STORAGE must be passed as a full program (wrapping one
        would mean inventing declarations the caller did not write).

        A compile failure is a RunResult with ``compiled_ok=False``, never an
        exception — that is the expected outcome for CICS source (Tier-1
        verification unavailable, CLAUDE.md decision 3). A MISSING ``cobc``, by
        contrast, still raises RuntimeError: that is a broken environment, not a
        fact about the code.
        """
        return _harness.run_cobol(_wrap_snippet(snippet), inputs)

    # -- ToolLayer: regulations (Track C owns) ------------------------------

    def search_regulations(self, query: str) -> list[RegSearchHit]:
        # Delegate to Track C's clause-anchored search service (T3.3). Built and
        # held on first use (it loads the retrieval models), keeping this facade
        # method thin; the pinned default mode/HyDE are RegulationSearch's.
        from cobol_archaeologist.rag.search import RegulationSearch

        if getattr(self, "_reg_search", None) is None:
            self._reg_search = RegulationSearch()
        return self._reg_search.search(query, k=5)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _child(node, type_: str):
    return next((c for c in node.children if c.type == type_), None)


def _text(node) -> str | None:
    return node.text.decode(errors="replace") if node is not None else None


def _redefines_name(node) -> str | None:
    clause = _child(node, "redefines_clause")
    if clause is None:
        return None
    word = _dataflow._first_qualified_word(clause)
    if word is None:
        return None
    words = _dataflow._words(word)
    return words[0] if words else None


def _wrap_snippet(snippet: str) -> str:
    if _ID_DIVISION_RE.search(snippet):
        return snippet
    body_lines = []
    for line in snippet.splitlines():
        if not line.strip():
            body_lines.append("")
        elif line.startswith("       "):  # already fixed-format (Area A at col 8)
            body_lines.append(line)
        else:
            body_lines.append("           " + line.strip())
    return _SNIPPET_SHELL.format(body="\n".join(body_lines))
