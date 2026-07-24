"""Deterministic fixture-backed ToolLayer implementation (Track C, T3.5).

The stub independently reproduces the T1.6 consumer semantics used by the
agent: original-source reads, 60-line code/copybook caps with full pointers,
case-insensitive lookup/search, empty caller/callee lists for unknown
paragraphs, ``paragraph=""`` for external program entries, and typed lookup
errors for unknown required names.

Tier-1 divergence is explicit: this offline stub does not invoke GnuCOBOL.  It
can deterministically emulate literal ``DISPLAY`` statements, while CICS or
other unsupported snippets return ``compiled_ok=False``.  That return is the
same "Tier 1 unavailable" meaning as RealToolLayer's CICS compile failure; the
stub cannot reproduce RealToolLayer's environment-level missing-``cobc``
RuntimeError because it intentionally has no compiler dependency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from cobol_archaeologist.schemas import RegulationClause
from cobol_archaeologist.tool_types import (
    CODE_CAP_LINES,
    CopybookExpansion,
    DataLayout,
    DefUseSite,
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
    SliceStatement,
    SourceRef,
    VariableTrace,
)
from cobol_archaeologist.tools import ToolLookupError

DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "agent" / "corpus"
)
GREP_CAP_MATCHES = 200
_PROGRAM_ID_RE = re.compile(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"^ {7}([A-Z0-9][A-Z0-9-]*)\.\s*$", re.IGNORECASE)
_LEVEL_RE = re.compile(
    r"^\s*(\d{2}|77|88)\s+([A-Z0-9-]+)"
    r"(?:\s+REDEFINES\s+([A-Z0-9-]+))?.*?"
    r"(?:\s+PIC\s+([A-Z0-9()VXS9+\-]+))?(?:\s|\.|$)",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class _Paragraph:
    name: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class _Program:
    program: str
    path: Path
    lines: tuple[str, ...]
    paragraphs: tuple[_Paragraph, ...]


class StubToolLayer:
    """Small, deterministic ToolLayer over a committed COBOL fixture corpus."""

    def __init__(self, corpus_root: Path = DEFAULT_CORPUS) -> None:
        self.corpus_root = Path(corpus_root)
        self._programs = self._load_programs()
        if not self._programs:
            raise ValueError(f"no COBOL fixtures under {self.corpus_root}")
        self._copybooks = {
            path.stem.upper(): path
            for path in sorted(self.corpus_root.iterdir())
            if path.is_file() and path.suffix.lower() in {".cpy", ".copy"}
        }
        clause_path = self.corpus_root / "clauses.jsonl"
        self._clauses = [
            RegulationClause.model_validate(json.loads(line))
            for line in clause_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self._edges = self._build_edges()

    # -- discovery ---------------------------------------------------------

    def _load_programs(self) -> dict[str, _Program]:
        programs: dict[str, _Program] = {}
        if not self.corpus_root.is_dir():
            return programs
        for path in sorted(self.corpus_root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".cbl", ".cob"}:
                continue
            lines = tuple(path.read_text(encoding="utf-8").splitlines())
            match = _PROGRAM_ID_RE.search("\n".join(lines))
            if match is None:
                continue
            program = match.group(1).upper()
            headers = [
                (i, m.group(1).upper())
                for i, line in enumerate(lines, start=1)
                if (m := _PARAGRAPH_RE.match(line))
            ]
            paragraphs = tuple(
                _Paragraph(
                    name=name,
                    line_start=start,
                    line_end=(headers[index + 1][0] - 1)
                    if index + 1 < len(headers)
                    else len(lines),
                )
                for index, (start, name) in enumerate(headers)
            )
            programs[program] = _Program(program, path, lines, paragraphs)
        return programs

    def _key(self, program: str) -> str:
        key = Path(program).stem.upper()
        if key not in self._programs:
            raise ToolLookupError(
                f"unknown program {program!r} (fixture: {self.corpus_root})"
            )
        return key

    def _program(self, program: str) -> _Program:
        return self._programs[self._key(program)]

    def _paragraph(self, program: _Program, name: str) -> _Paragraph | None:
        wanted = name.upper()
        return next((p for p in program.paragraphs if p.name == wanted), None)

    def _paragraph_for_line(self, program: _Program, line: int) -> str | None:
        para = next(
            (p for p in program.paragraphs if p.line_start <= line <= p.line_end),
            None,
        )
        return para.name if para else None

    # -- call graph --------------------------------------------------------

    def _build_edges(self) -> dict[tuple[str, str], list[NodeRef]]:
        edges: dict[tuple[str, str], list[NodeRef]] = {}
        for program in self._programs.values():
            known = {p.name for p in program.paragraphs}
            for para in program.paragraphs:
                code = "\n".join(
                    program.lines[para.line_start - 1 : para.line_end]
                ).upper()
                targets: list[NodeRef] = []
                for pattern in (
                    r"\bPERFORM\s+([A-Z0-9-]+)",
                    r"\bGO\s+TO\s+([A-Z0-9-]+)",
                ):
                    for target in re.findall(pattern, code):
                        if target in known:
                            targets.append(
                                NodeRef(program=program.program, paragraph=target)
                            )
                for target in re.findall(r"\bCALL\s+['\"]([A-Z0-9-]+)['\"]", code):
                    targets.append(NodeRef(program=target.upper(), paragraph=""))
                edges[(program.program, para.name)] = _dedupe_nodes(targets)
        return edges

    # -- ToolLayer: reads --------------------------------------------------

    def read_paragraph(self, program: str, name: str) -> ParagraphView:
        prog = self._program(program)
        para = self._paragraph(prog, name)
        if para is None:
            raise ToolLookupError(
                f"unknown paragraph {name!r} in program {program!r}"
            )
        lines = prog.lines[para.line_start - 1 : para.line_end]
        return ParagraphView(
            ref=SourceRef(
                program=prog.program,
                paragraph=para.name,
                line_start=para.line_start,
                line_end=para.line_end,
            ),
            name=para.name,
            code="\n".join(lines[:CODE_CAP_LINES]),
            truncated=len(lines) > CODE_CAP_LINES,
            callers=self.find_callers(prog.program, para.name),
            callees=self.find_callees(prog.program, para.name),
        )

    def read_program(self, program: str) -> ProgramView:
        prog = self._program(program)
        return ProgramView(
            program=prog.program,
            path=str(prog.path),
            paragraphs=[
                ParagraphSpan(
                    name=p.name, line_start=p.line_start, line_end=p.line_end
                )
                for p in prog.paragraphs
            ],
        )

    def find_callers(self, program: str, para: str) -> list[NodeRef]:
        key = self._key(program)
        wanted = para.upper()
        if self._paragraph(self._programs[key], wanted) is None:
            return []
        callers = [
            NodeRef(program=source_program, paragraph=source_para)
            for (source_program, source_para), targets in self._edges.items()
            if NodeRef(program=key, paragraph=wanted) in targets
        ]
        return _dedupe_nodes(callers)

    def find_callees(self, program: str, para: str) -> list[NodeRef]:
        key = self._key(program)
        wanted = para.upper()
        if self._paragraph(self._programs[key], wanted) is None:
            return []
        return list(self._edges.get((key, wanted), []))

    # -- ToolLayer: trace/slice -------------------------------------------

    def trace_variable(
        self, var: str, program: str | None = None
    ) -> VariableTrace:
        variable = var.upper()
        scoped = self._key(program) if program is not None else None
        sources: list[tuple[str, Path, _Program | None]] = []
        for key, prog in sorted(self._programs.items()):
            if scoped is None or key == scoped:
                sources.append((key, prog.path, prog))
        if scoped is None:
            sources.extend(
                (name, path, None) for name, path in sorted(self._copybooks.items())
            )

        matcher = re.compile(
            rf"(?<![A-Z0-9-]){re.escape(variable)}(?![A-Z0-9-])",
            re.IGNORECASE,
        )
        sites: list[DefUseSite] = []
        for label, path, prog in sources:
            for lineno, text in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not matcher.search(text):
                    continue
                kind, statement_kind = _def_use_kind(text, variable)
                sites.append(
                    DefUseSite(
                        kind=kind,
                        ref=SourceRef(
                            program=label,
                            paragraph=self._paragraph_for_line(prog, lineno)
                            if prog
                            else None,
                            line_start=lineno,
                            line_end=lineno,
                        ),
                        statement_kind=statement_kind,
                        excerpt=text.strip(),
                    )
                )
        return VariableTrace(
            variable=variable, scoped_program=scoped, sites=sites
        )

    def slice_on(self, var: str, program: str | None = None) -> Slice:
        trace = self.trace_variable(var, program)
        statements = [
            SliceStatement(ref=site.ref, text=site.excerpt) for site in trace.sites
        ]
        paragraphs = _dedupe_nodes(
            [
                NodeRef(program=site.ref.program, paragraph=site.ref.paragraph)
                for site in trace.sites
                if site.ref.paragraph is not None
            ]
        )
        return Slice(
            variable=trace.variable,
            scoped_program=trace.scoped_program,
            statements=statements,
            paragraphs=paragraphs,
            is_interprocedural=(
                len({node.program for node in paragraphs}) > 1
                or len(paragraphs) > 1
            ),
        )

    # -- ToolLayer: copybooks/layout --------------------------------------

    def resolve_copybook(self, name: str) -> CopybookExpansion:
        key = Path(name).stem.upper()
        try:
            path = self._copybooks[key]
        except KeyError:
            raise ToolLookupError(f"unknown copybook {name!r}") from None
        lines = path.read_text(encoding="utf-8").splitlines()
        return CopybookExpansion(
            name=key,
            text="\n".join(lines[:CODE_CAP_LINES]),
            truncated=len(lines) > CODE_CAP_LINES,
            line_map=[
                LineMapEntry(
                    expanded_start=1,
                    expanded_end=len(lines),
                    source_file=str(path),
                    source_line_start=1,
                )
            ],
        )

    def get_data_layout(self, record: str) -> DataLayout:
        wanted = record.upper()
        for label, path in self._searchable_files():
            lines = path.read_text(encoding="utf-8").splitlines()
            declarations = [
                (lineno, match)
                for lineno, line in enumerate(lines, start=1)
                if (match := _LEVEL_RE.match(line))
            ]
            for index, (lineno, match) in enumerate(declarations):
                if match.group(2).upper() != wanted:
                    continue
                head_level = int(match.group(1))
                root = _field_from_match(match)
                stack: list[tuple[int, FieldLayout]] = [(head_level, root)]
                line_end = lineno
                for child_line, child_match in declarations[index + 1 :]:
                    level = int(child_match.group(1))
                    if level <= head_level and level != 88:
                        break
                    field = _field_from_match(child_match)
                    if level == 88:
                        stack[-1][1].children.append(field)
                    else:
                        while len(stack) > 1 and stack[-1][0] >= level:
                            stack.pop()
                        stack[-1][1].children.append(field)
                        stack.append((level, field))
                    line_end = child_line
                return DataLayout(
                    record=wanted,
                    root=root,
                    source=SourceRef(
                        program=label,
                        line_start=lineno,
                        line_end=line_end,
                    ),
                )
        raise ToolLookupError(f"unknown record {record!r}")

    # -- ToolLayer: search/run --------------------------------------------

    def grep(self, pattern: str) -> GrepResult:
        regex = re.compile(pattern, re.IGNORECASE)
        matches: list[GrepMatch] = []
        truncated = False
        for label, path in self._searchable_files():
            for lineno, text in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not regex.search(text):
                    continue
                if len(matches) >= GREP_CAP_MATCHES:
                    truncated = True
                    break
                matches.append(
                    GrepMatch(program=label, line=lineno, text=text.rstrip())
                )
            if truncated:
                break
        return GrepResult(pattern=pattern, matches=matches, truncated=truncated)

    def run_cobol(
        self, snippet: str, inputs: RunInputs | None = None
    ) -> RunResult:
        # DECISION (offline Tier 1): never pretend unsupported code executed;
        # return the same compiled_ok=False "unavailable" signal as real CICS.
        del inputs
        if re.search(r"\bEXEC\s+CICS\b", snippet, re.IGNORECASE):
            return RunResult(
                compiled_ok=False,
                stderr="Tier-1 unavailable: offline stub does not compile CICS",
            )
        displays = re.findall(
            r"\bDISPLAY\s+['\"]([^'\"]*)['\"]", snippet, re.IGNORECASE
        )
        if displays:
            return RunResult(
                compiled_ok=True,
                stdout="\n".join(displays) + "\n",
                exit_code=0,
            )
        return RunResult(
            compiled_ok=False,
            stderr="Tier-1 unavailable: snippet is outside the stub DISPLAY emulator",
        )

    def search_regulations(self, query: str) -> list[RegSearchHit]:
        query_tokens = set(_WORD_RE.findall(query.lower()))
        if not query_tokens:
            return []
        hits: list[RegSearchHit] = []
        for clause in self._clauses:
            tokens = set(_WORD_RE.findall(clause.text.lower()))
            overlap = len(query_tokens & tokens)
            if overlap:
                hits.append(
                    RegSearchHit(clause=clause, score=overlap / len(query_tokens))
                )
        return sorted(
            hits,
            key=lambda hit: (-hit.score, hit.clause.doc, hit.clause.clause_id),
        )[:5]

    def _searchable_files(self) -> list[tuple[str, Path]]:
        programs = [
            (key, program.path) for key, program in sorted(self._programs.items())
        ]
        copybooks = sorted(self._copybooks.items())
        return programs + copybooks


def _dedupe_nodes(nodes: list[NodeRef]) -> list[NodeRef]:
    result: list[NodeRef] = []
    seen: set[tuple[str, str]] = set()
    for node in nodes:
        key = (node.program, node.paragraph)
        if key not in seen:
            seen.add(key)
            result.append(node)
    return result


def _def_use_kind(text: str, variable: str) -> tuple[str, str]:
    upper = text.upper()
    escaped = re.escape(variable)
    if re.search(rf"\bACCEPT\s+{escaped}\b", upper):
        return "def", "ACCEPT"
    if re.search(rf"\bCOMPUTE\s+{escaped}\b", upper):
        return "def", "COMPUTE"
    if re.search(rf"\bMOVE\b.*\bTO\s+{escaped}\b", upper):
        return "def", "MOVE"
    if _LEVEL_RE.match(text):
        return "def", "VALUE-clause" if " VALUE " in upper else "data-declaration"
    keyword = next(
        (
            word
            for word in ("IF", "COMPUTE", "MOVE", "DISPLAY", "PERFORM")
            if re.search(rf"\b{word}\b", upper)
        ),
        "statement",
    )
    return "use", keyword


def _field_from_match(match: re.Match[str]) -> FieldLayout:
    return FieldLayout(
        name=match.group(2).upper(),
        level=int(match.group(1)),
        pic=match.group(4),
        redefines=match.group(3).upper() if match.group(3) else None,
    )
