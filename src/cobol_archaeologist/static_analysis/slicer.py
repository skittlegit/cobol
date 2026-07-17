"""Backward program slicer (Track A, T1.4 — milestone M1).

``slice_on(var, programs, call_graph, program=None)`` returns the minimal
cross-paragraph statement set affecting ``var``: a backward slice over data
dependence + control dependence, with interprocedural glue so scattered COBOL
reads as one coherent "rule".

Design: data dependence is computed from AST def/use (reusing T1.3
``dataflow`` classification); control dependence is read off the T1.1
``Statement`` nesting (guarding IF/EVALUATE/WHEN/PERFORM-loop ancestors). The
two views are joined by original source line.

Semantics (normative, per the T1.4 work order):
1. Data dependence is transitive to a fixpoint (no depth cap): every def of a
   worklist variable is included and that def's used identifiers join the
   worklist.
2. Control dependence: an included statement pulls in its guarding conditions,
   and identifiers in those conditions join the worklist.
3. Interprocedural glue: when the slice spans paragraphs, the PERFORM/GO TO
   statements connecting them (call-graph paths from an entry point) are
   included.
4. DATA DIVISION VALUE-clause defs of sliced variables are included as
   statements (original-source text via the T1.1 LineMap).
5. ``?ambiguous`` T1.3 sites are included (conservative), never dropped.

Out of scope (inherits T1.3): forward slicing, LINKAGE/COMMAREA value flow,
minimality proofs, CBSA.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from cobol_archaeologist.parser.paragraphs import Program, Statement
from cobol_archaeologist.static_analysis import dataflow as _df
from cobol_archaeologist.tool_types import NodeRef, Slice, SliceStatement, SourceRef

# Stop condition: a slice this large is almost certainly ambiguity blow-up.
_MAX_SLICE_STATEMENTS = 150

_CONTAINER_KINDS = frozenset({"IF", "ELSE", "EVALUATE", "WHEN", "PERFORM_LOOP"})
_FLOW_EDGE_KINDS = frozenset({"perform", "goto"})


class SliceBlowupError(RuntimeError):
    """Raised when a slice exceeds the statement cap (T1.4 stop condition)."""


@dataclass
class _Unit:
    """One statement in one program, joined across the AST/Statement views."""
    program: str
    paragraph: str
    line_start: int
    line_end: int
    kind: str
    def_ids: frozenset[int]
    use_ids: frozenset[int]
    cond_use_ids: frozenset[int]
    guards: tuple[int, ...]          # line_starts of guarding container units
    text: str
    is_container: bool
    target: str | None = None        # PERFORM_CALL / GOTO target paragraph


@dataclass
class _ProgramModel:
    program: Program
    symbols: object
    units: list[_Unit]
    by_line: dict[int, _Unit] = dc_field(default_factory=dict)

    def __post_init__(self):
        for u in self.units:
            self.by_line.setdefault(u.line_start, u)


# --------------------------------------------------------------------------
# Building the per-program unit model
# --------------------------------------------------------------------------

def _resolve_ids(refs, symbols) -> frozenset[int]:
    ids: set[int] = set()
    for ref in refs:
        for target in _df._ref_targets(ref, symbols):
            ids.add(id(target))
    return frozenset(ids)


def _build_model(program: Program, search_paths: list[Path]) -> _ProgramModel:
    symbols = _df.build_symbols(program, search_paths)
    program_path = Path(program.path)
    source = program_path.read_text(encoding="utf-8", errors="replace")
    tree = _df._parser().parse(_df.preprocess(source).text.encode())
    proc = _df._procedure_division(tree.root_node)

    ast_defuse: dict[int, tuple[frozenset[int], frozenset[int]]] = {}
    ast_cond: dict[int, frozenset[int]] = {}
    if proc is not None:
        for node in _df._iter_nodes(proc):
            classified = _df._classify(node)
            if classified is not None:
                _kind, uses, defs = classified
                line = node.start_point[0] + 1
                u_ids = _resolve_ids(uses, symbols)
                d_ids = _resolve_ids(defs, symbols)
                if line in ast_defuse:
                    pu, pd = ast_defuse[line]
                    ast_defuse[line] = (pu | u_ids, pd | d_ids)
                else:
                    ast_defuse[line] = (u_ids, d_ids)
            cond = _df._condition_uses(node)
            if cond:
                # Key EVALUATE's subject by the evaluate_header line so it aligns
                # with the EVALUATE Statement; other hosts key by their own line.
                key_line = node.start_point[0] + 1
                if node.type == "evaluate_subject" and node.parent is not None:
                    key_line = node.parent.start_point[0] + 1
                ids = _resolve_ids(cond, symbols)
                ast_cond[key_line] = ast_cond.get(key_line, frozenset()) | ids

    units: list[_Unit] = []

    def make_unit(stmt: Statement, guards: tuple[int, ...]) -> _Unit:
        line = stmt.ref.line_start
        uses, defs = ast_defuse.get(line, (frozenset(), frozenset()))
        cond_ids = ast_cond.get(line, frozenset())
        para = stmt.ref.paragraph or _df._paragraph_of(program, line) or ""
        unit = _Unit(
            program=program.program_id, paragraph=para,
            line_start=line, line_end=stmt.ref.line_end, kind=stmt.kind,
            def_ids=defs, use_ids=uses, cond_use_ids=cond_ids, guards=guards,
            text=_df._excerpt(program_path, line, stmt.ref.line_end),
            is_container=stmt.kind in _CONTAINER_KINDS, target=stmt.target,
        )
        units.append(unit)
        return unit

    def walk(stmts: list[Statement], guards: tuple[int, ...]) -> None:
        prev_if_line: int | None = None
        for stmt in stmts:
            unit = make_unit(stmt, guards)
            key = stmt.ref.line_start
            if stmt.kind == "IF":
                walk(stmt.children, guards + (key,))
                prev_if_line = key
            elif stmt.kind == "ELSE":
                # DECISION: T1.1 emits IF and ELSE as *siblings*, so an ELSE
                # body's guarding condition is the paired IF's — a preceding
                # sibling, not a Statement-tree ancestor. We thread that IF's
                # line in as the ELSE's guard so control dependence still pulls
                # the deciding condition (and `else_if_header` chains, which
                # T1.1 nests as ELSE→IF, resolve naturally through recursion).
                paired = guards + ((prev_if_line,) if prev_if_line is not None else ())
                unit.guards = paired
                walk(stmt.children, paired)
            elif stmt.kind in ("EVALUATE", "WHEN", "PERFORM_LOOP"):
                walk(stmt.children, guards + (key,))

    for para in program.paragraphs:
        walk(para.statements, ())

    return _ProgramModel(program=program, symbols=symbols, units=units)


# --------------------------------------------------------------------------
# The slice fixpoint (data + control dependence)
# --------------------------------------------------------------------------

def _slice_program(var: str, model: _ProgramModel) -> tuple[list[_Unit], set[int]]:
    targets = _df._resolve_targets(var, model.symbols)
    if not targets:
        return [], set()
    worklist: set[int] = {id(t) for t in targets}
    sliced_vars: set[int] = set()
    included: dict[int, _Unit] = {}  # line_start -> unit

    def include(unit: _Unit) -> None:
        if unit.line_start in included:
            return
        included[unit.line_start] = unit
        if len(included) > _MAX_SLICE_STATEMENTS:
            raise SliceBlowupError(
                f"slice of {var!r} in {model.program.program_id} exceeded "
                f"{_MAX_SLICE_STATEMENTS} statements — likely ambiguity blow-up")
        for gline in unit.guards:
            guard = model.by_line.get(gline)
            if guard is not None:
                include(guard)
                worklist.update(guard.cond_use_ids - sliced_vars)
        worklist.update((unit.use_ids | unit.cond_use_ids) - sliced_vars)

    while worklist:
        v = worklist.pop()
        if v in sliced_vars:
            continue
        sliced_vars.add(v)
        for unit in model.units:
            if v in unit.def_ids:
                include(unit)

    return list(included.values()), sliced_vars


# --------------------------------------------------------------------------
# Interprocedural glue
# --------------------------------------------------------------------------

def _flow_adjacency(call_graph, program_id: str) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    if call_graph is None:
        return adj
    for edge in call_graph.edges:
        if (edge.source.program == program_id and edge.target.program == program_id
                and edge.edge_kind in _FLOW_EDGE_KINDS):
            adj.setdefault(edge.source.paragraph, []).append(edge.target.paragraph)
    return adj


def _glue_units(model: _ProgramModel, included_paras: set[str], call_graph) -> list[_Unit]:
    """PERFORM_CALL/GOTO units connecting an entry point to each included
    paragraph, so the slice reads as one top-down flow.

    DECISION: interprocedural glue threads each included paragraph back to a
    program entry point along the shortest call-graph flow path (PERFORM/GO TO
    edges), rather than only linking included paragraphs pairwise. This
    naturally includes the driver PERFORMs that fan out to sibling paragraphs
    (e.g. <preamble> → 2000 → 2700) so the slice is a coherent flow. Glue is
    skipped for single-paragraph slices, keeping trivial slices minimal.
    """
    if call_graph is None or len(included_paras) <= 1:
        return []
    adj = _flow_adjacency(call_graph, model.program.program_id)
    # DECISION (T1.2b/F7): glue BFS starts from the roots of the PERFORM/GO TO
    # flow forest — the first paragraph plus any paragraph with no incoming
    # PERFORM/GO TO edge. This used to be `call_graph.entry_points`, but F7
    # redefined that to the single true program entry (for D6). We reconstruct
    # the old flow-forest-root set locally from `adj` (which is exactly the
    # PERFORM/GO TO adjacency) so glue paths still reach every included paragraph.
    para_order = [p.span.name for p in model.program.paragraphs]
    flow_targets = {t for targets in adj.values() for t in targets}
    entries = (
        [para_order[0]] + [p for p in para_order[1:] if p not in flow_targets]
        if para_order else []
    )

    # Call units indexed by (source_paragraph, target_paragraph).
    call_units: dict[tuple[str, str], _Unit] = {}
    for u in model.units:
        if u.kind in ("PERFORM_CALL", "GOTO") and u.target is not None:
            call_units.setdefault((u.paragraph, u.target), u)

    glue: dict[int, _Unit] = {}
    for target in included_paras:
        path = _shortest_path(adj, entries, target)
        if path is None:
            continue
        for src, dst in zip(path, path[1:]):
            unit = call_units.get((src, dst))
            if unit is not None:
                glue[unit.line_start] = unit
    return list(glue.values())


def _shortest_path(adj: dict[str, list[str]], starts: list[str], goal: str) -> list[str] | None:
    if goal in starts:
        return [goal]
    seen = set(starts)
    queue: deque[list[str]] = deque([s] for s in starts)
    while queue:
        path = queue.popleft()
        for nxt in adj.get(path[-1], []):
            if nxt == goal:
                return path + [nxt]
            if nxt not in seen:
                seen.add(nxt)
                queue.append(path + [nxt])
    return None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _value_decl_statements(sliced_vars: set[int], model: _ProgramModel) -> list[SliceStatement]:
    out: list[SliceStatement] = []
    for fld in model.symbols.fields:
        if id(fld) in sliced_vars and fld.has_value and not fld.is_condition:
            out.append(SliceStatement(
                ref=fld.decl_ref,
                text=_df._excerpt(fld.decl_path, fld.decl_ref.line_start, fld.decl_ref.line_end)))
    return out


def slice_on(
    var: str,
    programs: list[Program],
    call_graph=None,
    program: str | None = None,
) -> Slice:
    """Backward slice of ``var``. ``program=None`` -> corpus-wide (union over
    every program declaring the field); ``program=<id>`` -> that program only
    (contract amendment A2)."""
    statements: list[SliceStatement] = []

    for prog in programs:
        if program is not None and prog.program_id != program:
            continue
        model = _build_model(prog, _df._search_paths(Path(prog.path)))
        units, sliced_vars = _slice_program(var, model)
        if not units and not sliced_vars:
            continue

        included_paras = {u.paragraph for u in units}
        glue = _glue_units(model, included_paras, call_graph)
        all_units = {u.line_start: u for u in units}
        for gu in glue:
            all_units.setdefault(gu.line_start, gu)

        for u in all_units.values():
            statements.append(SliceStatement(
                ref=SourceRef(program=u.program, paragraph=u.paragraph,
                              line_start=u.line_start, line_end=u.line_end),
                text=u.text))

        statements.extend(_value_decl_statements(sliced_vars, model))

    # Order: (program, original line); de-dup by (program, line). The worklist
    # fixpoint is set-based (inclusion order is nondeterministic), so both the
    # statement list and the paragraph list are derived from this stable sort.
    unique: dict[tuple[str, int, int], SliceStatement] = {}
    for st in statements:
        unique[(st.ref.program, st.ref.line_start, st.ref.line_end)] = st
    ordered = sorted(unique.values(), key=lambda s: (s.ref.program, s.ref.line_start, s.ref.line_end))

    paragraphs: list[NodeRef] = []
    seen_para: set[tuple[str, str]] = set()
    for st in ordered:
        if not st.ref.paragraph:
            continue
        key = (st.ref.program, st.ref.paragraph)
        if key not in seen_para:
            seen_para.add(key)
            paragraphs.append(NodeRef(program=st.ref.program, paragraph=st.ref.paragraph))

    is_interprocedural = len(seen_para) > 1

    return Slice(
        variable=var, scoped_program=program, statements=ordered,
        paragraphs=paragraphs, is_interprocedural=is_interprocedural,
    )
