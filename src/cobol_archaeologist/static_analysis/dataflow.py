"""Interprocedural def-use analysis (Track A, T1.3).

For any data item, ``trace_variable`` returns every definition and use site
across the parsed corpus — the backing for the contract's
``trace_variable(var, program=None)`` and the input to T1.4 slicing.

Classification is AST-based: the tree-sitter tree is walked directly (this
module re-parses from ``Program.path`` rather than leaning on ``Statement``,
so def/use precision is independent of the paragraph model). Def/use follows
the normative table in the T1.3 work order.

Name resolution:
- ``X OF Y`` resolves to the field named X whose ancestor chain includes Y;
  a bare unique X resolves plainly; a bare X declared in several records of one
  program yields all candidate sites, ``statement_kind`` suffixed
  ``"?ambiguous"`` (never a silent guess).
- REDEFINES: when the traced field's storage overlaps a redefining/redefined
  declaration, one ``statement_kind="REDEFINES-alias"`` def-site is added at
  the redefining declaration. Full alias analysis (writes through the alias
  flowing to the traced field) is OUT OF SCOPE.
- An 88-level condition name used in a condition counts as a **use of its
  parent field**.

Documented limitations (out of scope, candidate follow-ups):
- Subscripts / reference modification: ``X(I:L)`` traces as ``X`` — the index
  and length identifiers are not emitted as their own sites.
- Inter-program data flow through LINKAGE / COMMAREA is not modeled; a
  corpus-wide trace unions per-program sites by field name, it does not thread
  a value across a CALL/LINK/XCTL boundary.
- STRING/UNSTRING source operands are not tracked as uses (only the INTO
  targets are defs), per the normative table.

Copybook search paths are derived from each program's path using the CardDemo
layout (``app/cbl/X.cbl`` -> ``app/cpy``, ``app/cpy-bms``).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from functools import lru_cache
from pathlib import Path

from tree_sitter import Node, Parser

from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.parser._grammar import get_language
from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.parser.paragraphs import Program
from cobol_archaeologist.tool_types import (
    DefUseSite,
    LineMapEntry,
    SourceRef,
    VariableTrace,
)

_COPYBOOK_EXTS = (".cpy", ".cbl")

# Condition/arithmetic-expression node types whose identifiers are all uses.
_CONDITION_HOSTS = ("if_header", "else_if_header", "when", "evaluate_subject")


# --------------------------------------------------------------------------
# Symbol table
# --------------------------------------------------------------------------


@dataclass
class Field:
    name: str
    level: int
    is_condition: bool  # 88-level condition name
    ancestors: tuple[str, ...]  # immediate parent first, up to the 01/77 record
    record: str
    parent: Field | None  # for 88: the field it qualifies; else structural parent
    decl_ref: SourceRef  # original-source declaration site
    decl_path: Path  # file the declaration lives in (for excerpt reading)
    has_value: bool
    redefines: str | None  # name of the field this one REDEFINES
    redefined_by: list[str] = dc_field(default_factory=list)


@dataclass
class ProgramSymbols:
    program_id: str
    program_path: Path
    fields: list[Field]

    def by_name(self, name: str) -> list[Field]:
        up = name.upper()
        return [f for f in self.fields if f.name.upper() == up]


def _parser() -> Parser:
    p = Parser()
    p.set_language(get_language())
    return p


def _search_paths(program_path: Path) -> list[Path]:
    # DECISION: trace_variable's signature carries no search_paths, so copybook
    # dirs are derived from the CardDemo layout (app/cbl/X.cbl -> app/cpy,
    # app/cpy-bms). A non-CardDemo corpus (e.g. CBSA at T1.6) would need this
    # generalized; recorded as a layout assumption rather than hardcoding paths.
    app = program_path.parent.parent
    return [app / "cpy", app / "cpy-bms"]


def _map_expanded_line(
    line_map: list[LineMapEntry], expanded_line: int
) -> tuple[str, int]:
    """(source_file, original_line) for an expanded-text line via the LineMap."""
    for entry in line_map:
        if entry.expanded_start <= expanded_line <= entry.expanded_end:
            return entry.source_file, entry.source_line_start + (
                expanded_line - entry.expanded_start
            )
    return "", expanded_line


def _child(node: Node, type_: str) -> Node | None:
    return next((c for c in node.children if c.type == type_), None)


def _entry_name(node: Node) -> str | None:
    en = _child(node, "entry_name")
    return en.text.decode(errors="replace").strip() if en else None


def build_symbols(program: Program, search_paths: list[Path]) -> ProgramSymbols:
    program_path = Path(program.path)
    source = program_path.read_text(encoding="utf-8", errors="replace")
    exp = expand(source, search_paths)
    tree = _parser().parse(exp.text.encode())

    # Stem -> resolved path, for reading declaration excerpts from copybooks.
    file_paths: dict[str, Path] = {program.program_id.upper(): program_path}
    for base in search_paths:
        if base.is_dir():
            for entry in base.iterdir():
                if entry.is_file() and entry.suffix.lower() in _COPYBOOK_EXTS:
                    file_paths.setdefault(entry.stem.upper(), entry)

    descriptions: list[Node] = []

    def walk(n: Node) -> None:
        if n.type == "data_description":
            descriptions.append(n)
        for c in n.children:
            walk(c)

    walk(tree.root_node)

    fields: list[Field] = []
    by_name: dict[str, list[Field]] = {}
    stack: list[Field] = []  # structural ancestors (non-88), innermost last

    for node in descriptions:
        level_node = _child(node, "level_number")
        name = _entry_name(node)
        if level_node is None or name is None:
            continue
        try:
            level = int(level_node.text.decode().strip())
        except ValueError:
            continue

        expanded_line = node.start_point[0] + 1
        source_file, original_line = _map_expanded_line(exp.line_map, expanded_line)
        # DECISION: SourceRef has only `program` (no separate file field), so a
        # declaration physically in a copybook records ref.program = the
        # copybook stem (e.g. "CVACT01Y"), and a program-own declaration records
        # the program id. This keeps every ref genuinely original-source and
        # lets the gate assert copybook provenance (LineMap round-trip).
        file_label = source_file.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        stem = (
            Path(file_label).stem.upper() if file_label else program.program_id.upper()
        )
        decl_path = file_paths.get(stem, program_path)
        ref_program = stem if file_label else program.program_id

        end_line = original_line + (node.end_point[0] - node.start_point[0])
        redefines_node = _child(node, "redefines_clause")
        redefines = None
        if redefines_node is not None:
            qw = _first_qualified_word(redefines_node)
            if qw is not None:
                redefines = _words(qw)[0]

        is_88 = level == 88
        if not is_88:
            while stack and stack[-1].level >= level:
                stack.pop()
        parent = stack[-1] if stack else None
        ancestors = tuple(f.name for f in reversed(stack))
        record = ancestors[-1] if ancestors else name

        fld = Field(
            name=name,
            level=level,
            is_condition=is_88,
            ancestors=ancestors,
            record=record,
            parent=parent,
            decl_ref=SourceRef(
                program=ref_program, line_start=original_line, line_end=end_line
            ),
            decl_path=decl_path,
            has_value=_child(node, "value_clause") is not None,
            redefines=redefines,
        )
        fields.append(fld)
        by_name.setdefault(name.upper(), []).append(fld)
        if not is_88:
            stack.append(fld)

    # Back-fill REDEFINES reverse edges.
    for fld in fields:
        if fld.redefines:
            for target in by_name.get(fld.redefines.upper(), []):
                target.redefined_by.append(fld.name)

    return ProgramSymbols(
        program_id=program.program_id, program_path=program_path, fields=fields
    )


# --------------------------------------------------------------------------
# Reference extraction
# --------------------------------------------------------------------------


def _words(qualified_word: Node) -> list[str]:
    return [
        c.text.decode(errors="replace")
        for c in qualified_word.children
        if c.type == "WORD"
    ]


def _first_qualified_word(node: Node) -> Node | None:
    if node.type == "qualified_word":
        return node
    for c in node.children:
        found = _first_qualified_word(c)
        if found is not None:
            return found
    return None


@dataclass(frozen=True)
class Ref:
    name: str
    qualifiers: tuple[str, ...]
    node: Node


def _ref_of(node: Node) -> Ref | None:
    """A single operand -> its base identifier reference (None for literals).

    The grammar emits a reference-modified/subscripted operand as SIBLING
    nodes — ``qualified_word`` (the base) followed by a standalone ``refmod``
    /``subref`` holding only the ``(start:len)``/``(index)`` expression. So a
    ``refmod``/``subref`` node contributes nothing (its index identifiers are
    not tracked — 'X(I:L) traces as X'); the base is captured from its sibling.
    ``arithmetic_x`` genuinely wraps its base, so it is unwrapped.
    """
    if node.type == "qualified_word":
        words = _words(node)
        if not words:
            return None
        return Ref(name=words[0], qualifiers=tuple(words[1:]), node=node)
    if node.type == "arithmetic_x":
        base = _first_qualified_word(node)
        return _ref_of(base) if base is not None else None
    return None


def _refs_in(node: Node) -> list[Ref]:
    """Every identifier reference in an expression subtree. Subscript/refmod
    index expressions are skipped ('X(I:L) traces as X'); the base identifier
    is a sibling ``qualified_word`` and is captured on its own."""
    out: list[Ref] = []

    def walk(n: Node) -> None:
        if n.type == "qualified_word":
            r = _ref_of(n)
            if r is not None:
                out.append(r)
            return
        if n.type in ("refmod", "subref"):
            return
        for c in n.children:
            walk(c)

    walk(node)
    return out


def _field_refs(node: Node, field_name: str) -> list[Ref]:
    return [
        r
        for r in map(_ref_of, node.children_by_field_name(field_name))
        if r is not None
    ]


# --------------------------------------------------------------------------
# Statement classification (normative table)
# --------------------------------------------------------------------------


def _classify(node: Node) -> tuple[str, list[Ref], list[Ref]] | None:
    """(statement_kind, uses, defs) for a procedure statement, or None."""
    t = node.type
    if t == "move_statement":
        return "MOVE", _field_refs(node, "src"), _field_refs(node, "dst")
    if t == "compute_statement":
        right = node.child_by_field_name("right")
        defs = [
            _ref_of(_first_qualified_word(c))
            for c in node.children_by_field_name("left")
        ]
        uses = _refs_in(right) if right is not None else []
        return "COMPUTE", uses, [d for d in defs if d is not None]
    # DECISION: arithmetic with GIVING -> the giving/remainder targets are the
    # only defs and all operands are uses; without GIVING the accumulator
    # (to/from/val2/into) is BOTH a use and a def (`ADD a TO b` reads and writes
    # b), so it is emitted as two sites — matching the normative table.
    if t == "add_statement":
        frm, to, giv = (
            _field_refs(node, "from"),
            _field_refs(node, "to"),
            _field_refs(node, "giving"),
        )
        return ("ADD", frm + to, giv) if giv else ("ADD", frm + to, to)
    if t == "subtract_statement":
        x, frm, giv = (
            _field_refs(node, "x"),
            _field_refs(node, "from"),
            _field_refs(node, "giving"),
        )
        return ("SUBTRACT", x + frm, giv) if giv else ("SUBTRACT", x + frm, frm)
    if t == "multiply_statement":
        v1, v2, giv = (
            _field_refs(node, "val1"),
            _field_refs(node, "val2"),
            _field_refs(node, "giving"),
        )
        return ("MULTIPLY", v1 + v2, giv) if giv else ("MULTIPLY", v1 + v2, v2)
    if t == "divide_statement":
        x, by, into = (
            _field_refs(node, "x"),
            _field_refs(node, "by"),
            _field_refs(node, "into"),
        )
        giv, rem = _field_refs(node, "giving"), _field_refs(node, "remainder")
        if giv:
            return "DIVIDE", x + by + into, giv + rem
        return "DIVIDE", x + into, into + rem
    if t == "initialize_statement":
        return "INITIALIZE", [], _field_refs(node, "x")
    if t == "accept_statement":
        return "ACCEPT", [], [r for r in map(_ref_of, node.children) if r is not None]
    if t == "set_statement":
        uses, defs = [], []
        for sub in node.children:
            if sub.type in ("set_to", "set_up_down"):
                defs += (
                    _field_refs(sub, "from")
                    if sub.type == "set_to"
                    else _field_refs(sub, "x")
                )
                uses += _field_refs(sub, "to")
                if sub.type == "set_up_down":
                    uses += _field_refs(sub, "by") + _field_refs(sub, "x")
            elif sub.type == "set_to_true_false":
                defs += _field_refs(sub, "x")
        return "SET", uses, defs
    if t == "read_statement":
        return "READ", [], _field_refs(node, "into")
    if t == "string_statement":
        return "STRING", [], _field_refs(node, "into")
    if t == "unstring_statement":
        defs: list[Ref] = []
        for item in node.children:
            if item.type == "unstring_into_item":
                defs += _field_refs(item, "x")
        return "UNSTRING", [], defs
    if t == "write_statement":
        return "WRITE", _field_refs(node, "from"), []
    if t == "display_statement":
        return "DISPLAY", [r for r in map(_ref_of, node.children) if r is not None], []
    return None


def _condition_uses(node: Node) -> list[Ref]:
    if node.type == "if_header" or node.type == "else_if_header":
        cond = node.child_by_field_name("condition")
        return _refs_in(cond) if cond is not None else []
    if node.type == "when":
        return _refs_in(node)
    if node.type == "evaluate_subject":
        return _refs_in(node)
    if node.type == "perform_statement_loop":
        opt = node.child_by_field_name("option")
        until = opt.child_by_field_name("until") if opt is not None else None
        return _refs_in(until) if until is not None else []
    return []


# --------------------------------------------------------------------------
# Resolution + tracing
# --------------------------------------------------------------------------


@lru_cache(maxsize=64)
def _read_lines(path_str: str) -> list[str]:
    return Path(path_str).read_text(encoding="utf-8", errors="replace").splitlines()


def _excerpt(path: Path, line_start: int, line_end: int) -> str:
    lines = _read_lines(str(path))
    chunk = lines[line_start - 1 : line_end]
    return "\n".join(s.rstrip() for s in chunk).strip()


def _resolve_targets(spec: str, symbols: ProgramSymbols) -> list[Field]:
    """Traced spec ('X' or 'X OF Y OF Z') -> candidate Fields in this program.
    An 88-level spec resolves to its parent field (use-of-parent semantics).

    COBOL names and the OF/IN qualifier keyword are case-insensitive, so the
    spec is upper-cased BEFORE splitting — splitting first would only match an
    already-uppercase " OF "/" IN " and silently return zero sites for
    `errmsgo of cosgn0ao` (review 2026-07-12, F5).
    """
    upper = spec.upper()
    parts = [p for p in upper.replace(" IN ", " OF ").split(" OF ") if p.strip()]
    primary = parts[0].strip()
    quals = [q.strip() for q in parts[1:]]
    cands = [f for f in symbols.fields if f.name.upper() == primary]
    if quals:
        cands = [
            f
            for f in cands
            if all(q in {a.upper() for a in f.ancestors} for q in quals)
        ]
    resolved: list[Field] = []
    for f in cands:
        target = f.parent if f.is_condition and f.parent is not None else f
        if target not in resolved:
            resolved.append(target)
    return resolved


def _ref_targets(ref: Ref, symbols: ProgramSymbols) -> list[Field]:
    spec = (
        ref.name
        if not ref.qualifiers
        else ref.name + " OF " + " OF ".join(ref.qualifiers)
    )
    return _resolve_targets(spec, symbols)


def _procedure_division(root: Node) -> Node | None:
    if root.type == "procedure_division":
        return root
    for c in root.children:
        found = _procedure_division(c)
        if found is not None:
            return found
    return None


def _paragraph_of(program: Program, line: int) -> str | None:
    for para in program.paragraphs:
        if para.span.line_start <= line <= para.span.line_end:
            return para.span.name
    return None


def _analyze_program(
    spec: str, program: Program, search_paths: list[Path]
) -> list[DefUseSite]:
    symbols = build_symbols(program, search_paths)
    targets = _resolve_targets(spec, symbols)
    if not targets:
        return []
    target_set = {id(t) for t in targets}
    ambiguous = len({(t.name, t.record) for t in targets}) > 1
    program_path = Path(program.path)

    sites: list[DefUseSite] = []

    # Declaration-side sites: VALUE-clause defs and REDEFINES-alias markers.
    for t in targets:
        if t.has_value and not t.is_condition:
            sites.append(
                DefUseSite(
                    kind="def",
                    ref=t.decl_ref,
                    statement_kind=_amb("VALUE-clause", ambiguous),
                    excerpt=_excerpt(
                        t.decl_path, t.decl_ref.line_start, t.decl_ref.line_end
                    ),
                )
            )
        for alias in _redefines_aliases(t, symbols):
            sites.append(
                DefUseSite(
                    kind="def",
                    ref=alias.decl_ref,
                    statement_kind="REDEFINES-alias",
                    excerpt=_excerpt(
                        alias.decl_path,
                        alias.decl_ref.line_start,
                        alias.decl_ref.line_end,
                    ),
                )
            )

    # Procedure-side def/use.
    source = program_path.read_text(encoding="utf-8", errors="replace")
    tree = _parser().parse(preprocess(source).text.encode())
    proc = _procedure_division(tree.root_node)
    if proc is not None:
        for node in _iter_nodes(proc):
            classified = _classify(node)
            if classified is not None:
                kind, uses, defs = classified
                _emit(
                    sites,
                    uses,
                    "use",
                    kind,
                    node,
                    program,
                    program_path,
                    symbols,
                    target_set,
                    ambiguous,
                )
                _emit(
                    sites,
                    defs,
                    "def",
                    kind,
                    node,
                    program,
                    program_path,
                    symbols,
                    target_set,
                    ambiguous,
                )
            cond_uses = _condition_uses(node)
            if cond_uses:
                ckind = (
                    "PERFORM-UNTIL"
                    if node.type == "perform_statement_loop"
                    else node.type.replace("_header", "")
                    .replace("_subject", "")
                    .upper()
                )
                _emit(
                    sites,
                    cond_uses,
                    "use",
                    ckind,
                    node,
                    program,
                    program_path,
                    symbols,
                    target_set,
                    ambiguous,
                )

    return sites


def _emit(
    sites, refs, kind, stmt_kind, node, program, program_path, symbols, target_set, amb
) -> None:
    for ref in refs:
        rtargets = _ref_targets(ref, symbols)
        if not any(id(t) in target_set for t in rtargets):
            continue
        line = node.start_point[0] + 1
        end = node.end_point[0] + 1
        ref_ambiguous = amb or len({(t.name, t.record) for t in rtargets}) > 1
        sites.append(
            DefUseSite(
                kind=kind,
                ref=SourceRef(
                    program=program.program_id,
                    paragraph=_paragraph_of(program, line),
                    line_start=line,
                    line_end=end,
                ),
                statement_kind=_amb(stmt_kind, ref_ambiguous),
                excerpt=_excerpt(program_path, line, end),
            )
        )


def _amb(kind: str, ambiguous: bool) -> str:
    return kind + "?ambiguous" if ambiguous else kind


def _redefines_aliases(target: Field, symbols: ProgramSymbols) -> list[Field]:
    out: list[Field] = []
    if target.redefines:
        out += [f for f in symbols.by_name(target.redefines) if f is not target]
    for other in symbols.fields:
        if other.redefines and other.redefines.upper() == target.name.upper():
            out.append(other)
    # De-dup by declaration identity.
    seen: set[int] = set()
    unique: list[Field] = []
    for f in out:
        if id(f) not in seen:
            seen.add(id(f))
            unique.append(f)
    return unique


def _iter_nodes(root: Node):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def trace_variable(
    var: str,
    programs: list[Program],
    call_graph=None,
    program: str | None = None,
) -> VariableTrace:
    """Every def/use site of ``var`` across ``programs``.

    ``program=None`` -> corpus-wide (union over every program that declares the
    field); ``program=<id>`` -> that program only (contract amendment A2).
    ``call_graph`` is accepted for signature stability (interprocedural value
    flow is T1.4's concern); def-use itself is per-statement.
    """
    sites: list[DefUseSite] = []
    for prog in programs:
        if program is not None and prog.program_id != program:
            continue
        sites.extend(_analyze_program(var, prog, _search_paths(Path(prog.path))))

    sites.sort(
        key=lambda s: (
            s.ref.program,
            s.ref.line_start,
            s.ref.line_end,
            s.kind,
            s.statement_kind,
        )
    )
    return VariableTrace(variable=var, scoped_program=program, sites=sites)
