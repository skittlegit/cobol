"""AST-backed paragraph/statement extraction (Track A, T1.1).

Grammar facts (validated against the pinned tree-sitter-cobol grammar,
`e99dbdc3d800…`, on the CardDemo gate corpus): there is no ``paragraph``
container node and no ``if_statement``/``evaluate_statement`` wrapper either —
``paragraph_header``, ``if_header``/``else_header``/``else_if_header``/
``END_IF``, ``evaluate_header``/``when``/``END_EVALUATE``, and
``perform_statement_loop``/``END_PERFORM`` are all flat siblings directly
under ``procedure_division``, in source order. Paragraph spans and statement
nesting are both reconstructed here from that flat stream.

DECISION: parse_program runs `cleaner.preprocess` directly on the program's
own original source (no `copybooks.expand` in this pipeline). All 10 gate
programs reach zero ERROR nodes from masking alone (COACTUPC's procedure-
division `COPY ... REPLACING` included) — expansion isn't needed for span/
nesting correctness, and inlining copybook-sourced statements would require
attributing a `Statement.ref` to a different file than `tool_types.SourceRef`
represents (program+line only). `copybooks.expand` is gated independently
(T1.1 gate #5) for the data-layout/field-resolution use case; wiring it into
paragraph extraction is left for whichever later task needs copybook-sourced
procedure statements (would need a CONTRACT discussion first).
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from cobol_archaeologist import tool_types
from cobol_archaeologist.ingest.cleaner import preprocess

STATEMENT_KINDS = (
    "IF",
    "ELSE",
    "EVALUATE",
    "WHEN",
    "PERFORM_CALL",
    "PERFORM_LOOP",
    "GOTO",
    "CALL",
    "MOVE",
    "COMPUTE",
    "OTHER",
)

# CALL 'literal' program-name node types (vs. dynamic CALL identifier).
_LITERAL_TARGET_TYPES = ("string", "h_string", "n_string")

# DECISION (T1.2): batch programs place unnamed "main driver" code directly
# under PROCEDURE DIVISION, before the first paragraph header — it holds the
# root PERFORM edges the call graph needs. Rather than change T1.1's paragraph
# set (its gate asserts exact spans), parse_program(include_preamble=True)
# opt-in surfaces that code as one synthetic leading paragraph named below.
# Angle brackets are illegal in COBOL names, so this never collides with a real
# paragraph; the default (False) keeps T1.1 behaviour and fixtures unchanged.
PREAMBLE_NAME = "<preamble>"

_BOUNDARY_TYPES = ("paragraph_header", "section_header")
_PROGRAM_ID_RE = re.compile(
    r"PROGRAM-ID\.\s+([A-Za-z0-9][A-Za-z0-9_-]*)", re.IGNORECASE
)
_PARA_HEADER_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\s*\.\s*$", re.IGNORECASE)
_PROCEDURE_DIVISION_RE = re.compile(r"^\s*PROCEDURE\s+DIVISION\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\s+SECTION\s*\.\s*$", re.IGNORECASE)
_SCOPE_TERMINATOR_RE = re.compile(r"^END-[A-Z-]+$", re.IGNORECASE)
_NON_PARAGRAPH_LABELS = {"END", "EXIT", "GOBACK", "STOP", "CONTINUE"}


class Statement(BaseModel):
    kind: str
    ref: tool_types.SourceRef
    children: list[Statement] = []
    target: str | None = None
    thru_target: str | None = None
    dynamic: bool = False  # CALL identifier (target resolved at runtime) -> True


class Paragraph(BaseModel):
    span: tool_types.ParagraphSpan
    statements: list[Statement] = []


class Program(BaseModel):
    program_id: str
    path: str
    paragraphs: list[Paragraph] = []


def _extract_program_id(source: str) -> str:
    m = _PROGRAM_ID_RE.search(source)
    return m.group(1).upper() if m else ""


def _clean_label(node) -> str:
    return node.text.decode(errors="replace").split(".")[0].strip()


def _line_start(node) -> int:
    return node.start_point[0] + 1


def _line_end(node) -> int:
    return node.end_point[0] + 1


def _extract_perform_targets(node) -> tuple[str | None, str | None]:
    procedure = next((c for c in node.children if c.type == "perform_procedure"), None)
    if procedure is None:
        return None, None
    labels = [c for c in procedure.children if c.type == "label"]
    if not labels:
        return None, None
    target = labels[0].text.decode(errors="replace").strip()
    thru_target = (
        labels[1].text.decode(errors="replace").strip() if len(labels) > 1 else None
    )
    return target, thru_target


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in ("'", '"') and text[-1] == text[0]:
        return text[1:-1]
    return text


def _extract_goto_target(node) -> str | None:
    """First (and, in CardDemo, only) GO TO target label.

    DECISION: the grammar's ``to`` field is multi-valued to model computed
    ``GO TO a b c DEPENDING ON n``; CardDemo has zero DEPENDING GO TOs
    (verified corpus-wide), so a single target is faithful. A computed GO TO
    would need a multi-target Statement shape — noted as a limitation, not
    built, since nothing exercises it.
    """
    label = node.child_by_field_name("to")
    if label is None:
        return None
    return label.text.decode(errors="replace").strip()


def _extract_call_target(node) -> tuple[str | None, bool]:
    """(target, dynamic) for a CALL. Literal ``CALL 'X'`` -> ('X', False);
    dynamic ``CALL identifier`` -> (None, True)."""
    x = node.child_by_field_name("x")
    if x is None:
        return None, False
    if x.type in _LITERAL_TARGET_TYPES:
        return _strip_quotes(x.text.decode(errors="replace")), False
    return None, True


def _classify(node_type: str) -> str:
    if node_type == "perform_statement_call_proc":
        return "PERFORM_CALL"
    if node_type == "move_statement":
        return "MOVE"
    if node_type == "compute_statement":
        return "COMPUTE"
    return "OTHER"


def _block_end_line(header_node, body: list[Statement]) -> int:
    return body[-1].ref.line_end if body else _line_end(header_node)


_IF_CHAIN_STOP = frozenset({"else_header", "else_if_header", "END_IF"})


def _parse_if_chain(
    nodes: list,
    i: int,
    program_id: str,
    paragraph: str,
) -> tuple[list[Statement], int]:
    """Consume one IF/ELSE-IF/ELSE/END-IF construct starting at ``nodes[i]``.

    DECISION: the grammar fuses a bare "ELSE" whose sole content is a nested
    "IF" into one ``else_if_header`` node — but the source still writes a
    real nested IF with its own END-IF (COBOL has no "ELSE IF" keyword;
    verified against CBTRN02C.cbl:350-356, two END-IFs for two nesting
    levels). So ``else_if_header`` recurses into this same function rather
    than being treated as a same-level chained branch.
    """
    header = nodes[i]
    n = len(nodes)
    body, i = _build_statements(nodes, i + 1, _IF_CHAIN_STOP, program_id, paragraph)
    ref = tool_types.SourceRef(
        program=program_id,
        paragraph=paragraph,
        line_start=_line_start(header),
        line_end=_block_end_line(header, body),
    )
    result = [Statement(kind="IF", ref=ref, children=body)]

    if i < n and nodes[i].type == "else_header":
        else_node = nodes[i]
        ebody, i = _build_statements(
            nodes, i + 1, frozenset({"END_IF"}), program_id, paragraph
        )
        eref = tool_types.SourceRef(
            program=program_id,
            paragraph=paragraph,
            line_start=_line_start(else_node),
            line_end=_block_end_line(else_node, ebody),
        )
        result.append(Statement(kind="ELSE", ref=eref, children=ebody))
    elif i < n and nodes[i].type == "else_if_header":
        else_if_node = nodes[i]
        nested, i = _parse_if_chain(nodes, i, program_id, paragraph)
        eref = tool_types.SourceRef(
            program=program_id,
            paragraph=paragraph,
            line_start=_line_start(else_if_node),
            line_end=nested[-1].ref.line_end,
        )
        result.append(Statement(kind="ELSE", ref=eref, children=nested))

    # Shared close: a bare IF/END-IF falls through to here directly; the
    # else_header/else_if_header branches leave their own END_IF unconsumed
    # (the else_if_header recursion already consumed *its* inner END_IF).
    if i < n and nodes[i].type == "END_IF":
        i += 1

    return result, i


def _build_statements(
    nodes: list,
    start: int,
    stop_types: frozenset[str],
    program_id: str,
    paragraph: str,
) -> tuple[list[Statement], int]:
    stmts: list[Statement] = []
    i = start
    n = len(nodes)
    while i < n:
        node = nodes[i]
        t = node.type

        if t in stop_types or t in _BOUNDARY_TYPES:
            return stmts, i

        if t in ("if_header", "else_if_header"):
            branch_stmts, i = _parse_if_chain(nodes, i, program_id, paragraph)
            stmts.extend(branch_stmts)
            continue

        if t == "evaluate_header":
            when_stmts: list[Statement] = []
            j = i + 1
            while j < n and nodes[j].type not in ("END_EVALUATE", *_BOUNDARY_TYPES):
                if nodes[j].type in ("when", "when_other"):
                    wnode = nodes[j]
                    wbody, j = _build_statements(
                        nodes,
                        j + 1,
                        frozenset({"when", "when_other", "END_EVALUATE"}),
                        program_id,
                        paragraph,
                    )
                    wref = tool_types.SourceRef(
                        program=program_id,
                        paragraph=paragraph,
                        line_start=_line_start(wnode),
                        line_end=_block_end_line(wnode, wbody),
                    )
                    when_stmts.append(Statement(kind="WHEN", ref=wref, children=wbody))
                else:
                    j += 1
            end_line = _block_end_line(node, when_stmts)
            if j < n and nodes[j].type == "END_EVALUATE":
                end_line = _line_end(nodes[j])
                j += 1
            ref = tool_types.SourceRef(
                program=program_id,
                paragraph=paragraph,
                line_start=_line_start(node),
                line_end=end_line,
            )
            stmts.append(Statement(kind="EVALUATE", ref=ref, children=when_stmts))
            i = j
            continue

        if t == "perform_statement_loop":
            body, j = _build_statements(
                nodes, i + 1, frozenset({"END_PERFORM"}), program_id, paragraph
            )
            end_line = _block_end_line(node, body)
            if j < n and nodes[j].type == "END_PERFORM":
                end_line = _line_end(nodes[j])
                j += 1
            ref = tool_types.SourceRef(
                program=program_id,
                paragraph=paragraph,
                line_start=_line_start(node),
                line_end=end_line,
            )
            stmts.append(Statement(kind="PERFORM_LOOP", ref=ref, children=body))
            i = j
            continue

        if t == "perform_statement_call_proc":
            target, thru_target = _extract_perform_targets(node)
            ref = tool_types.SourceRef(
                program=program_id,
                paragraph=paragraph,
                line_start=_line_start(node),
                line_end=_line_end(node),
            )
            stmts.append(
                Statement(
                    kind="PERFORM_CALL", ref=ref, target=target, thru_target=thru_target
                )
            )
            i += 1
            continue

        if t == "goto_statement":
            ref = tool_types.SourceRef(
                program=program_id,
                paragraph=paragraph,
                line_start=_line_start(node),
                line_end=_line_end(node),
            )
            stmts.append(
                Statement(kind="GOTO", ref=ref, target=_extract_goto_target(node))
            )
            i += 1
            continue

        if t == "call_statement":
            target, dynamic = _extract_call_target(node)
            ref = tool_types.SourceRef(
                program=program_id,
                paragraph=paragraph,
                line_start=_line_start(node),
                line_end=_line_end(node),
            )
            stmts.append(
                Statement(kind="CALL", ref=ref, target=target, dynamic=dynamic)
            )
            i += 1
            continue

        if t.endswith("_statement"):
            ref = tool_types.SourceRef(
                program=program_id,
                paragraph=paragraph,
                line_start=_line_start(node),
                line_end=_line_end(node),
            )
            stmts.append(Statement(kind=_classify(t), ref=ref))
            i += 1
            continue

        i += 1

    return stmts, i


def _find_procedure_division(root):
    if root.type == "procedure_division":
        return root
    for child in root.children:
        found = _find_procedure_division(child)
        if found is not None:
            return found
    return None


def _parse_ast(
    path: Path, program_id: str, include_preamble: bool = False
) -> list[Paragraph]:
    from tree_sitter import Parser

    from cobol_archaeologist.parser._grammar import get_language

    source = path.read_text(encoding="utf-8", errors="replace")
    pre = preprocess(source)
    parser = Parser()
    parser.set_language(get_language())
    tree = parser.parse(pre.text.encode())

    division = _find_procedure_division(tree.root_node)
    if division is None:
        return []

    children = division.children
    boundaries = [
        (idx, node) for idx, node in enumerate(children) if node.type in _BOUNDARY_TYPES
    ]
    para_boundaries = [
        (idx, node) for idx, node in boundaries if node.type == "paragraph_header"
    ]

    paragraphs: list[Paragraph] = []

    if include_preamble:
        first_boundary_idx = boundaries[0][0] if boundaries else len(children)
        preamble_stmts, _ = _build_statements(
            children,
            0,
            frozenset(),
            program_id,
            PREAMBLE_NAME,
        )
        if preamble_stmts:
            start_line = preamble_stmts[0].ref.line_start
            end_line = (
                _line_start(children[first_boundary_idx]) - 1
                if first_boundary_idx < len(children)
                else _line_end(division)
            )
            paragraphs.append(
                Paragraph(
                    span=tool_types.ParagraphSpan(
                        name=PREAMBLE_NAME,
                        line_start=start_line,
                        line_end=end_line,
                    ),
                    statements=preamble_stmts,
                )
            )

    for k, (idx, node) in enumerate(para_boundaries):
        name = _clean_label(node)
        start_line = _line_start(node)
        next_idx = next((bidx for bidx, _ in boundaries if bidx > idx), None)
        end_line = (
            _line_start(children[next_idx]) - 1
            if next_idx is not None
            else _line_end(division)
        )
        statements, _ = _build_statements(
            children,
            idx + 1,
            frozenset(),
            program_id,
            name,
        )
        paragraphs.append(
            Paragraph(
                span=tool_types.ParagraphSpan(
                    name=name, line_start=start_line, line_end=end_line
                ),
                statements=statements,
            )
        )
    return paragraphs


def _parse_regex(path: Path) -> list[Paragraph]:
    source = path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()
    in_procedure = False
    hits: list[tuple[str, int]] = []
    for lineno, ln in enumerate(lines, start=1):
        if len(ln) > 6 and ln[6] in ("*", "/"):
            continue
        body = ln[7:72] if len(ln) > 7 else ""
        if not in_procedure:
            if _PROCEDURE_DIVISION_RE.match(body):
                in_procedure = True
            continue
        # DECISION: a genuine paragraph header starts flush at col 8 (Area A);
        # statement continuations (e.g. a MOVE's target field wrapped onto its
        # own line) are indented into Area B and must not be mistaken for one.
        if body[:1].isspace():
            continue
        stripped = body.strip()
        m = _PARA_HEADER_RE.match(stripped)
        name = m.group(1).upper() if m else None
        if (
            m
            and name not in _NON_PARAGRAPH_LABELS
            and not _SCOPE_TERMINATOR_RE.match(name)
            and not _SECTION_RE.match(stripped)
        ):
            hits.append((name, lineno))

    last_content_line = len(lines)
    while last_content_line > 0:
        ln = lines[last_content_line - 1]
        if ln.strip() and not (len(ln) > 6 and ln[6] in ("*", "/")):
            break
        last_content_line -= 1

    paragraphs: list[Paragraph] = []
    for k, (name, start_line) in enumerate(hits):
        end_line = hits[k + 1][1] - 1 if k + 1 < len(hits) else last_content_line
        paragraphs.append(
            Paragraph(
                span=tool_types.ParagraphSpan(
                    name=name, line_start=start_line, line_end=end_line
                ),
                statements=[],
            )
        )
    return paragraphs


def parse_program(
    path: str | Path,
    backend: str = "ast",
    include_preamble: bool = False,
) -> Program:
    path = Path(path)
    source = path.read_text(encoding="utf-8", errors="replace")
    program_id = _extract_program_id(source)

    if backend == "regex":
        paragraphs = _parse_regex(path)
    elif backend == "ast":
        paragraphs = _parse_ast(path, program_id, include_preamble=include_preamble)
    else:
        raise ValueError(f"unknown backend: {backend!r}")

    return Program(program_id=program_id, path=str(path), paragraphs=paragraphs)
