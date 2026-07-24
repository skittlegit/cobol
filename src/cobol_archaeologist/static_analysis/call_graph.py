"""Call graph over parsed CardDemo programs (Track A, T1.2).

Edges:
- intra-program ``PERFORM``/``PERFORM a THRU b``/``GO TO`` (control flow);
- cross-program ``CALL 'literal'`` and CICS ``LINK``/``XCTL PROGRAM('lit')``.

The AST cannot see into masked ``EXEC`` blocks, so LINK/XCTL edges are
recovered by regex over ``PreprocessResult.masked_spans[*].original_text`` —
those blocks are rigidly formatted and this side-channel is the deliberate
design (CLAUDE.md locked decision + T1.2 work order), not a fallback.

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
from pathlib import Path

from pydantic import BaseModel, ConfigDict, PrivateAttr

from cobol_archaeologist.ingest.cleaner import PreprocessResult
from cobol_archaeologist.parser.paragraphs import Program, Statement
from cobol_archaeologist.tool_types import NodeRef, SourceRef

# LINK/XCTL side-channel patterns over verbatim EXEC text.
_LINK_XCTL_RE = re.compile(
    r"\bEXEC\s+CICS\b.*?\b(LINK|XCTL)\b", re.IGNORECASE | re.DOTALL
)
_PROGRAM_LITERAL_RE = re.compile(
    r"\bPROGRAM\s*\(\s*['\"]([A-Z0-9][A-Z0-9$#@_-]*)['\"]", re.IGNORECASE
)
_PROGRAM_ANY_RE = re.compile(r"\bPROGRAM\s*\(", re.IGNORECASE)

# Intra-program control-flow edges that carry reachability alongside fallthrough.
_FLOW_KINDS = frozenset({"perform", "goto"})

# Unconditional program-terminating verbs whose original-source text ends a
# paragraph's fall-through. GO TO is handled separately (it surfaces as a GOTO
# Statement kind); GOBACK/STOP RUN/EXIT PROGRAM classify as OTHER, so they are
# recognised by text. (DECISION in _last_stmt_is_transfer below.)
_GOBACK_RE = re.compile(r"\bGOBACK\b", re.IGNORECASE)
_STOP_RUN_RE = re.compile(r"\bSTOP\s+RUN\b", re.IGNORECASE)
_EXIT_PROGRAM_RE = re.compile(r"\bEXIT\s+PROGRAM\b", re.IGNORECASE)


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
    edge_kind: str  # perform | goto | call | link | xctl | fallthrough
    ref_line: int


class UnresolvedCall(BaseModel):
    ref: SourceRef
    reason: str


class LinkXctlShapeError(ValueError):
    """A masked EXEC span names LINK/XCTL but has no PROGRAM(...) — the T1.2
    stop condition: report, do not guess a parse."""


class CallGraph(BaseModel):
    edges: list[CallEdge]
    # Fall-through edges (paragraph N -> N+1 in source order) are kept OUT of
    # ``edges`` on purpose: ``callers``/``callees`` and the T1.2 golden adjacency
    # answer "who invokes this paragraph", which fall-through is not. Only
    # ``reachable_from``/``forest_roots`` consume them. Keeping the two lists
    # separate makes find_callers/find_callees bit-identical before/after F7.
    fallthrough_edges: list[CallEdge] = []
    unresolved: list[UnresolvedCall]
    # Ordered paragraph nodes per program (program order); backs THRU expansion
    # and entry-point detection.
    nodes_by_program: dict[str, list[NodeRef]]

    _out: dict[tuple[str, str], list[CallEdge]] = PrivateAttr(default_factory=dict)
    # Reachability adjacency: intra-program PERFORM/GO TO targets + fall-through
    # successors. Consumed by reachable_from only.
    _reach_out: dict[tuple[str, str], list[tuple[str, str]]] = PrivateAttr(
        default_factory=dict
    )
    # Every paragraph that is the target of ANY edge (perform/goto/call/link/
    # xctl/fallthrough). A forest root is a node absent from this set.
    _incoming_any: set[tuple[str, str]] = PrivateAttr(default_factory=set)

    def model_post_init(self, __context, /) -> None:
        for edge in self.edges:
            self._out.setdefault(
                (edge.source.program, edge.source.paragraph), []
            ).append(edge)
            self._incoming_any.add((edge.target.program, edge.target.paragraph))
            if (
                edge.edge_kind in _FLOW_KINDS
                and edge.source.program == edge.target.program
            ):
                self._reach_out.setdefault(
                    (edge.source.program, edge.source.paragraph), []
                ).append((edge.target.program, edge.target.paragraph))
        for edge in self.fallthrough_edges:
            self._incoming_any.add((edge.target.program, edge.target.paragraph))
            self._reach_out.setdefault(
                (edge.source.program, edge.source.paragraph), []
            ).append((edge.target.program, edge.target.paragraph))

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
            if (edge.target.program, edge.target.paragraph) == (
                node.program,
                node.paragraph,
            ):
                seen.add((edge.source.program, edge.source.paragraph))
        return [NodeRef(program=p, paragraph=q) for p, q in sorted(seen)]

    def reachable_from(self, entries: list[NodeRef]) -> set[NodeRef]:
        """Nodes reachable via control flow (PERFORM/GO TO **and fall-through**)
        — the basis for per-program dead-code detection.

        DECISION: cross-program edges (call/link/xctl) are NOT traversed for
        reachability. Within a program the only flow between paragraphs is
        PERFORM, GO TO, and sequential fall-through; cross-program entry happens
        through the callee's own entry points, so following call/link/xctl would
        conflate separate programs' reachability and defeat per-program
        dead-code analysis. Fall-through IS traversed (F7): a paragraph reached
        only by falling off the end of its predecessor must count as reachable.
        """
        visited: set[tuple[str, str]] = set()
        frontier = [(e.program, e.paragraph) for e in entries]
        while frontier:
            key = frontier.pop()
            if key in visited:
                continue
            visited.add(key)
            for nxt in self._reach_out.get(key, []):
                if nxt not in visited:
                    frontier.append(nxt)
        return {_h(p, q) for (p, q) in visited}

    def entry_points(self, program: str) -> list[NodeRef]:
        """The program's **true entry roots** only: ``<preamble>`` when present,
        else the first paragraph. Contrast ``forest_roots`` (F7 split).

        DECISION: this is the single point control enters the program. Isolated
        dead paragraphs used to be miscounted here as self-rooted entries (and so
        as reachable), which would make D6 (dead compliance code) miss its exact
        target; ``forest_roots`` now carries that "no incoming edge" query. COBOL
        ``ENTRY`` statements would add alternate entries, but CardDemo has none;
        if one is encountered it is a documented limitation (see
        docs/tasks/T1.6-work-order.md), not silently handled here.
        """
        nodes = self.nodes_by_program.get(program, [])
        return [nodes[0]] if nodes else []

    def forest_roots(self, program: str) -> list[NodeRef]:
        """Paragraphs with **no incoming edge of any kind** (perform/goto/call/
        link/xctl/fallthrough), excluding the true entry — the D6 dead-code
        candidates, in program order.

        An isolated dead paragraph lands here; a paragraph reached only by
        fall-through does not (it has an incoming fallthrough edge). D6 detection
        (Track C) consumes this together with ``reachable_from``.
        """
        nodes = self.nodes_by_program.get(program, [])
        if not nodes:
            return []
        entry_keys = {(e.program, e.paragraph) for e in self.entry_points(program)}
        roots: list[NodeRef] = []
        for node in nodes:
            key = (node.program, node.paragraph)
            if key in entry_keys:
                continue
            if key not in self._incoming_any:
                roots.append(node)
        return roots


def _flatten(statements: list[Statement]):
    for stmt in statements:
        yield stmt
        yield from _flatten(stmt.children)


def _first_paragraph(
    program_id: str, nodes_by_program: dict[str, list[NodeRef]]
) -> str:
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


def _read_source_lines(path: str) -> list[str] | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _stmt_text(stmt: Statement, source_lines: list[str]) -> str:
    lo = max(stmt.ref.line_start - 1, 0)
    hi = min(stmt.ref.line_end, len(source_lines))
    return "\n".join(source_lines[lo:hi])


def _last_stmt_is_transfer(stmt: Statement, source_lines: list[str] | None) -> bool:
    """Does this (paragraph-final, top-level) statement unconditionally transfer
    control, so no fall-through follows?

    DECISION: detected from the statement's ORIGINAL-source text rather than the
    grammar's goback/stop/exit-program node types. The call graph consumes the
    parsed ``Statement`` stream (kind + original line ref), not raw tree-sitter
    nodes — a top-level ``GO TO`` already surfaces as ``kind == "GOTO"`` (and a
    top-level GO TO is by definition unconditional), while GOBACK / STOP RUN /
    EXIT PROGRAM all classify as ``OTHER``. Re-parsing solely to reclassify those
    three terminal verbs would duplicate the parse, so we read their line text.
    When the source is unreadable we return False (conservative: add the
    fall-through edge — the safe over-approximation for D6).
    """
    if stmt.kind == "GOTO":
        return True
    if stmt.kind != "OTHER" or source_lines is None:
        return False
    text = _stmt_text(stmt, source_lines)
    return bool(
        _GOBACK_RE.search(text)
        or _STOP_RUN_RE.search(text)
        or _EXIT_PROGRAM_RE.search(text)
    )


def _fallthrough_edges(program: Program) -> list[CallEdge]:
    """Edge paragraph N -> N+1 in source order unless N ends in an unconditional
    transfer. Conservative: an empty paragraph, or one whose final-statement
    shape we cannot read, still gets the edge."""
    pid = program.program_id
    source_lines = _read_source_lines(program.path)
    edges: list[CallEdge] = []
    paras = program.paragraphs
    for i in range(len(paras) - 1):
        cur, nxt = paras[i], paras[i + 1]
        last = cur.statements[-1] if cur.statements else None
        if last is not None and _last_stmt_is_transfer(last, source_lines):
            continue
        edges.append(
            CallEdge(
                source=NodeRef(program=pid, paragraph=cur.span.name),
                target=NodeRef(program=pid, paragraph=nxt.span.name),
                edge_kind="fallthrough",
                ref_line=cur.span.line_end,
            )
        )
    return edges


def build_call_graph(
    programs: list[Program],
    preprocess_results: dict[str, PreprocessResult],
) -> CallGraph:
    nodes_by_program: dict[str, list[NodeRef]] = {
        prog.program_id: [
            NodeRef(program=prog.program_id, paragraph=p.span.name)
            for p in prog.paragraphs
        ]
        for prog in programs
    }
    # Fast membership: which paragraph names exist per program, and their order.
    para_order: dict[str, list[str]] = {
        pid: [n.paragraph for n in nodes] for pid, nodes in nodes_by_program.items()
    }
    para_set: dict[str, set[str]] = {
        pid: set(names) for pid, names in para_order.items()
    }

    edges: list[CallEdge] = []
    fallthrough_edges: list[CallEdge] = []
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

        _handle_link_xctl(
            program, preprocess_results.get(pid), nodes_by_program, edges, unresolved
        )
        fallthrough_edges.extend(_fallthrough_edges(program))

    return CallGraph(
        edges=edges,
        fallthrough_edges=fallthrough_edges,
        unresolved=unresolved,
        nodes_by_program=nodes_by_program,
    )


def _handle_perform(stmt, src, pid, names, order, edges, unresolved) -> None:
    target = stmt.target
    if target is None:
        unresolved.append(
            UnresolvedCall(ref=stmt.ref, reason="PERFORM with no resolvable target")
        )
        return
    if stmt.thru_target is None:
        if target in names:
            edges.append(
                CallEdge(
                    source=src,
                    target=NodeRef(program=pid, paragraph=target),
                    edge_kind="perform",
                    ref_line=stmt.ref.line_start,
                )
            )
        else:
            unresolved.append(
                UnresolvedCall(
                    ref=stmt.ref, reason=f"PERFORM to unknown paragraph {target!r}"
                )
            )
        return
    # THRU: expand over paragraph order (THRU is positional).
    thru = stmt.thru_target
    if target not in names or thru not in names:
        unresolved.append(
            UnresolvedCall(
                ref=stmt.ref,
                reason=f"PERFORM {target!r} THRU {thru!r} with unknown endpoint",
            )
        )
        return
    lo, hi = order.index(target), order.index(thru)
    if lo > hi:
        unresolved.append(
            UnresolvedCall(
                ref=stmt.ref, reason=f"PERFORM {target!r} THRU {thru!r} spans backwards"
            )
        )
        return
    for name in order[lo : hi + 1]:
        edges.append(
            CallEdge(
                source=src,
                target=NodeRef(program=pid, paragraph=name),
                edge_kind="perform",
                ref_line=stmt.ref.line_start,
            )
        )


def _handle_goto(stmt, src, pid, names, edges, unresolved) -> None:
    target = stmt.target
    if target and target in names:
        edges.append(
            CallEdge(
                source=src,
                target=NodeRef(program=pid, paragraph=target),
                edge_kind="goto",
                ref_line=stmt.ref.line_start,
            )
        )
    else:
        unresolved.append(
            UnresolvedCall(ref=stmt.ref, reason=f"GO TO unknown paragraph {target!r}")
        )


def _handle_call(stmt, src, nodes_by_program, edges, unresolved) -> None:
    if stmt.dynamic or stmt.target is None:
        unresolved.append(
            UnresolvedCall(ref=stmt.ref, reason="dynamic CALL (identifier target)")
        )
        return
    edges.append(
        CallEdge(
            source=src,
            target=NodeRef(
                program=stmt.target,
                paragraph=_first_paragraph(stmt.target, nodes_by_program),
            ),
            edge_kind="call",
            ref_line=stmt.ref.line_start,
        )
    )


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
            unresolved.append(
                UnresolvedCall(
                    ref=SourceRef(
                        program=pid,
                        line_start=span.start_line,
                        line_end=span.start_line,
                    ),
                    reason=f"{kind.upper()} outside any paragraph",
                )
            )
            continue
        src = NodeRef(program=pid, paragraph=para)
        lit = _PROGRAM_LITERAL_RE.search(span.original_text)
        if lit:
            target_prog = lit.group(1).upper()
            edges.append(
                CallEdge(
                    source=src,
                    target=NodeRef(
                        program=target_prog,
                        paragraph=_first_paragraph(target_prog, nodes_by_program),
                    ),
                    edge_kind=kind,
                    ref_line=span.start_line,
                )
            )
        elif _PROGRAM_ANY_RE.search(span.original_text):
            unresolved.append(
                UnresolvedCall(
                    ref=SourceRef(
                        program=pid,
                        paragraph=para,
                        line_start=span.start_line,
                        line_end=span.start_line,
                    ),
                    reason=f"{kind.upper()} PROGRAM(identifier) — dynamic target",
                )
            )
        else:
            raise LinkXctlShapeError(
                f"{pid}:{span.start_line} {kind.upper()} span has no PROGRAM(...): "
                f"{span.original_text!r}"
            )
