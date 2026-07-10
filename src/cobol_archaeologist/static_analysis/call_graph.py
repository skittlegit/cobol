"""Call graph over parsed CardDemo programs (Track A, T1.2).

Edges:
- intra-program ``PERFORM``/``PERFORM a THRU b``/``GO TO`` (control flow);
- cross-program ``CALL 'literal'`` and CICS ``LINK``/``XCTL PROGRAM('lit')``.

The AST cannot see into masked ``EXEC`` blocks, so LINK/XCTL edges are
recovered by regex over ``PreprocessResult.masked_spans[*].original_text`` —
those blocks are rigidly formatted and this side-channel is the deliberate
design (CLAUDE.md locked decision + track brief), not a fallback.

Node identity is ``tool_types.NodeRef`` = (program_id, paragraph_name).
Anything the analysis cannot resolve to a concrete target — a dynamic
``CALL identifier``, an ``XCTL PROGRAM(ws-var)``, or a PERFORM/GO TO to a
paragraph that does not exist — is recorded in ``CallGraph.unresolved`` rather
than dropped.

Noted limitation (candidate for a later task, out of scope here): CICS pseudo-
conversational edges via ``RETURN TRANSID`` / ``START TRANSID`` are not modeled
— they are control transfers through the CICS transaction table, not lexical
call sites, and need the transaction→program map to resolve.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, PrivateAttr

from cobol_archaeologist.ingest.cleaner import PreprocessResult
from cobol_archaeologist.parser.paragraphs import Program, Statement
from cobol_archaeologist.tool_types import NodeRef, SourceRef

# LINK/XCTL side-channel patterns over verbatim EXEC text.
_LINK_XCTL_RE = re.compile(r"\bEXEC\s+CICS\b.*?\b(LINK|XCTL)\b", re.I | re.S)
_PROGRAM_LITERAL_RE = re.compile(r"\bPROGRAM\s*\(\s*['\"]([A-Z0-9][A-Z0-9$#@_-]*)['\"]", re.I)
_PROGRAM_ANY_RE = re.compile(r"\bPROGRAM\s*\(", re.I)

_FLOW_KINDS = frozenset({"perform", "goto"})


class _HNodeRef(NodeRef):
    """Hashable NodeRef for set membership (reachable_from).

    DECISION: tool_types.NodeRef is not frozen (so not hashable) and making it
    hashable is a CONTRACT change. This local frozen subclass supplies __hash__
    for the ``set[NodeRef]`` return of reachable_from without touching the
    contract type — instances still pass ``isinstance(_, NodeRef)``.
    """

    model_config = ConfigDict(frozen=True)


def _h(program: str, paragraph: str) -> _HNodeRef:
    return _HNodeRef(program=program, paragraph=paragraph)


class CallEdge(BaseModel):
    source: NodeRef
    target: NodeRef
    edge_kind: str  # perform | goto | call | link | xctl
    ref_line: int


class UnresolvedCall(BaseModel):
    ref: SourceRef
    reason: str


class LinkXctlShapeError(ValueError):
    """A masked EXEC span names LINK/XCTL but has no PROGRAM(...) — the T1.2
    stop condition: report, do not guess a parse."""


class CallGraph(BaseModel):
    edges: list[CallEdge]
    unresolved: list[UnresolvedCall]
    # Ordered paragraph nodes per program (program order); backs THRU expansion
    # and entry-point detection.
    nodes_by_program: dict[str, list[NodeRef]]

    _out: dict[tuple[str, str], list[CallEdge]] = PrivateAttr(default_factory=dict)
    _incoming_flow: set[tuple[str, str]] = PrivateAttr(default_factory=set)

    def model_post_init(self, __context) -> None:
        for edge in self.edges:
            self._out.setdefault((edge.source.program, edge.source.paragraph), []).append(edge)
            if edge.edge_kind in _FLOW_KINDS and edge.source.program == edge.target.program:
                self._incoming_flow.add((edge.target.program, edge.target.paragraph))

    # -- queries ---------------------------------------------------------

    def callees(self, node: NodeRef) -> list[NodeRef]:
        seen: list[NodeRef] = []
        keys: set[tuple[str, str]] = set()
        for edge in self._out.get((node.program, node.paragraph), []):
            key = (edge.target.program, edge.target.paragraph)
            if key not in keys:
                keys.add(key)
                seen.append(edge.target)
        return sorted(seen, key=lambda n: (n.program, n.paragraph))

    def callers(self, node: NodeRef) -> list[NodeRef]:
        seen: set[tuple[str, str]] = set()
        for edge in self.edges:
            if (edge.target.program, edge.target.paragraph) == (node.program, node.paragraph):
                seen.add((edge.source.program, edge.source.paragraph))
        return [NodeRef(program=p, paragraph=q) for p, q in sorted(seen)]

    def reachable_from(self, entries: list[NodeRef]) -> set[NodeRef]:
        """Nodes reachable via control flow (PERFORM/GO TO) — the basis for
        per-program dead-code detection.

        DECISION: cross-program edges (call/link/xctl) are NOT traversed for
        reachability. Within a program the only flow between paragraphs is
        PERFORM and GO TO; cross-program entry happens through the callee's own
        entry points, so following call/link/xctl would conflate separate
        programs' reachability and defeat per-program dead-code analysis.
        """
        visited: set[_HNodeRef] = set()
        frontier = [_h(e.program, e.paragraph) for e in entries]
        while frontier:
            node = frontier.pop()
            if node in visited:
                continue
            visited.add(node)
            for edge in self._out.get((node.program, node.paragraph), []):
                if edge.edge_kind in _FLOW_KINDS:
                    nxt = _h(edge.target.program, edge.target.paragraph)
                    if nxt not in visited:
                        frontier.append(nxt)
        return set(visited)

    def entry_points(self, program: str) -> list[NodeRef]:
        """First paragraph + any paragraph with no incoming PERFORM/GO TO edge
        from within the same program (the roots of the control-flow forest)."""
        nodes = self.nodes_by_program.get(program, [])
        if not nodes:
            return []
        entries: list[NodeRef] = [nodes[0]]
        chosen = {(nodes[0].program, nodes[0].paragraph)}
        for node in nodes[1:]:
            key = (node.program, node.paragraph)
            if key not in self._incoming_flow and key not in chosen:
                entries.append(node)
                chosen.add(key)
        return entries


def _flatten(statements: list[Statement]):
    for stmt in statements:
        yield stmt
        yield from _flatten(stmt.children)


def _first_paragraph(program_id: str, nodes_by_program: dict[str, list[NodeRef]]) -> str:
    # DECISION: a cross-program CALL/LINK/XCTL to a program outside the analyzed
    # set still yields a real edge, with paragraph="" meaning "program entry,
    # first paragraph unknown (program not parsed)". The edge is never dropped —
    # we know the target program even when we haven't loaded its paragraphs.
    nodes = nodes_by_program.get(program_id)
    return nodes[0].paragraph if nodes else ""


def _locate_paragraph(program: Program, line: int) -> str | None:
    for para in program.paragraphs:
        if para.span.line_start <= line <= para.span.line_end:
            return para.span.name
    return None


def build_call_graph(
    programs: list[Program],
    preprocess_results: dict[str, PreprocessResult],
) -> CallGraph:
    nodes_by_program: dict[str, list[NodeRef]] = {
        prog.program_id: [
            NodeRef(program=prog.program_id, paragraph=p.span.name) for p in prog.paragraphs
        ]
        for prog in programs
    }
    # Fast membership: which paragraph names exist per program, and their order.
    para_order: dict[str, list[str]] = {
        pid: [n.paragraph for n in nodes] for pid, nodes in nodes_by_program.items()
    }
    para_set: dict[str, set[str]] = {pid: set(names) for pid, names in para_order.items()}

    edges: list[CallEdge] = []
    unresolved: list[UnresolvedCall] = []

    for program in programs:
        pid = program.program_id
        names = para_set.get(pid, set())
        order = para_order.get(pid, [])

        for para in program.paragraphs:
            src = NodeRef(program=pid, paragraph=para.span.name)
            for stmt in _flatten(para.statements):
                if stmt.kind == "PERFORM_CALL":
                    _handle_perform(stmt, src, pid, names, order, edges, unresolved)
                elif stmt.kind == "GOTO":
                    _handle_goto(stmt, src, pid, names, edges, unresolved)
                elif stmt.kind == "CALL":
                    _handle_call(stmt, src, nodes_by_program, edges, unresolved)

        _handle_link_xctl(program, preprocess_results.get(pid), nodes_by_program, edges, unresolved)

    return CallGraph(edges=edges, unresolved=unresolved, nodes_by_program=nodes_by_program)


def _handle_perform(stmt, src, pid, names, order, edges, unresolved) -> None:
    target = stmt.target
    if target is None:
        unresolved.append(UnresolvedCall(ref=stmt.ref, reason="PERFORM with no resolvable target"))
        return
    if stmt.thru_target is None:
        if target in names:
            edges.append(CallEdge(
                source=src, target=NodeRef(program=pid, paragraph=target),
                edge_kind="perform", ref_line=stmt.ref.line_start,
            ))
        else:
            unresolved.append(UnresolvedCall(
                ref=stmt.ref, reason=f"PERFORM to unknown paragraph {target!r}"))
        return
    # THRU: expand over paragraph order (THRU is positional).
    thru = stmt.thru_target
    if target not in names or thru not in names:
        unresolved.append(UnresolvedCall(
            ref=stmt.ref, reason=f"PERFORM {target!r} THRU {thru!r} with unknown endpoint"))
        return
    lo, hi = order.index(target), order.index(thru)
    if lo > hi:
        unresolved.append(UnresolvedCall(
            ref=stmt.ref, reason=f"PERFORM {target!r} THRU {thru!r} spans backwards"))
        return
    for name in order[lo:hi + 1]:
        edges.append(CallEdge(
            source=src, target=NodeRef(program=pid, paragraph=name),
            edge_kind="perform", ref_line=stmt.ref.line_start,
        ))


def _handle_goto(stmt, src, pid, names, edges, unresolved) -> None:
    target = stmt.target
    if target and target in names:
        edges.append(CallEdge(
            source=src, target=NodeRef(program=pid, paragraph=target),
            edge_kind="goto", ref_line=stmt.ref.line_start,
        ))
    else:
        unresolved.append(UnresolvedCall(
            ref=stmt.ref, reason=f"GO TO unknown paragraph {target!r}"))


def _handle_call(stmt, src, nodes_by_program, edges, unresolved) -> None:
    if stmt.dynamic or stmt.target is None:
        unresolved.append(UnresolvedCall(ref=stmt.ref, reason="dynamic CALL (identifier target)"))
        return
    edges.append(CallEdge(
        source=src,
        target=NodeRef(program=stmt.target, paragraph=_first_paragraph(stmt.target, nodes_by_program)),
        edge_kind="call", ref_line=stmt.ref.line_start,
    ))


def _handle_link_xctl(program, pre, nodes_by_program, edges, unresolved) -> None:
    if pre is None:
        return
    pid = program.program_id
    for span in pre.masked_spans:
        m = _LINK_XCTL_RE.search(span.original_text)
        if m is None:
            continue
        kind = m.group(1).lower()  # link | xctl
        para = _locate_paragraph(program, span.start_line)
        if para is None:
            # Span outside any named paragraph (and no preamble node covering
            # it) — record rather than silently misattribute.
            unresolved.append(UnresolvedCall(
                ref=SourceRef(program=pid, line_start=span.start_line, line_end=span.start_line),
                reason=f"{kind.upper()} outside any paragraph"))
            continue
        src = NodeRef(program=pid, paragraph=para)
        lit = _PROGRAM_LITERAL_RE.search(span.original_text)
        if lit:
            target_prog = lit.group(1).upper()
            edges.append(CallEdge(
                source=src,
                target=NodeRef(
                    program=target_prog,
                    paragraph=_first_paragraph(target_prog, nodes_by_program),
                ),
                edge_kind=kind, ref_line=span.start_line,
            ))
        elif _PROGRAM_ANY_RE.search(span.original_text):
            unresolved.append(UnresolvedCall(
                ref=SourceRef(program=pid, paragraph=para,
                              line_start=span.start_line, line_end=span.start_line),
                reason=f"{kind.upper()} PROGRAM(identifier) — dynamic target"))
        else:
            raise LinkXctlShapeError(
                f"{pid}:{span.start_line} {kind.upper()} span has no PROGRAM(...): "
                f"{span.original_text!r}")
