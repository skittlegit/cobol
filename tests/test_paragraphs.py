"""T1.1 gate: preprocessor + AST parser + copybook expansion on 10 CardDemo
programs. Fixtures: tests/fixtures/paragraphs/<prog>.json — built by AST
extraction, cross-validated against an independent regex ground truth
(Area-A-column + COBOL-scope-terminator-aware), then hand-eyeballed against
source for CBTRN02C, COSGN00C, and COACTUPC (see assertions 1 and 3 below).
"""
import json
from pathlib import Path

import pytest
from tree_sitter import Parser

from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.parser._grammar import get_language
from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.parser.paragraphs import parse_program

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"
CBL_DIR = CARDDEMO / "app" / "cbl"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "paragraphs"
SEARCH_PATHS = [CARDDEMO / "app" / "cpy", CARDDEMO / "app" / "cpy-bms"]

GATE_PROGRAMS = [
    "CBTRN02C", "CBACT01C", "CBACT04C", "CBSTM03A", "COSGN00C",
    "COACTUPC", "COACTVWC", "COCRDUPC", "COTRN02C", "COUSR02C",
]

pytestmark = pytest.mark.skipif(
    not CARDDEMO.is_dir(), reason="corpora not fetched (run scripts/fetch_corpora.sh)",
)


def _find_program_file(name: str) -> Path:
    matches = list(CBL_DIR.glob(f"{name}.*"))
    matches = [m for m in matches if m.suffix.lower() in (".cbl",)]
    assert matches, f"no source file found for {name}"
    return matches[0]


def _load_fixture(name: str) -> list[tuple[str, int, int]]:
    data = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return [tuple(entry) for entry in data]


def _count_errors(node) -> int:
    total = 1 if node.type == "ERROR" else 0
    for child in node.children:
        total += _count_errors(child)
    return total


@pytest.mark.parametrize("name", GATE_PROGRAMS)
def test_paragraph_spans_match_fixture(name):
    """Assertion 1: exact paragraph-set + span match per program."""
    path = _find_program_file(name)
    program = parse_program(path, backend="ast")
    actual = [(p.span.name, p.span.line_start, p.span.line_end) for p in program.paragraphs]
    assert actual == _load_fixture(name)


@pytest.mark.parametrize("name", GATE_PROGRAMS)
def test_zero_error_nodes_after_preprocessing(name):
    """Assertion 2: zero ERROR nodes after preprocessing, all 10."""
    path = _find_program_file(name)
    source = path.read_text(encoding="utf-8", errors="replace")
    pre = preprocess(source)
    parser = Parser()
    parser.set_language(get_language())
    tree = parser.parse(pre.text.encode())
    assert _count_errors(tree.root_node) == 0


def test_if_inside_if_nesting_cbtrn02c():
    """Assertion 3a: hand-verified IF-inside-IF, CBTRN02C.cbl:357-368.

    Source (1-indexed):
        357  IF APPL-AOK
        358      CONTINUE
        359  ELSE
        360      IF APPL-EOF
        361          MOVE 'Y' TO END-OF-FILE
        362      ELSE
        363          DISPLAY 'ERROR READING DALYTRAN FILE'
        364          MOVE DALYTRAN-STATUS TO IO-STATUS
        365          PERFORM 9910-DISPLAY-IO-STATUS
        366          PERFORM 9999-ABEND-PROGRAM
        367      END-IF
        368  END-IF
    """
    path = _find_program_file("CBTRN02C")
    program = parse_program(path, backend="ast")
    para = next(p for p in program.paragraphs if p.span.name == "1000-DALYTRAN-GET-NEXT")

    outer_if = next(s for s in para.statements if s.kind == "IF" and s.ref.line_start == 357)
    assert outer_if.ref.line_end == 358
    assert [c.kind for c in outer_if.children] == ["OTHER"]

    outer_else = next(s for s in para.statements if s.kind == "ELSE" and s.ref.line_start == 359)
    assert outer_else.ref.line_end == 366
    assert [c.kind for c in outer_else.children] == ["IF", "ELSE"]

    inner_if, inner_else = outer_else.children
    # DECISION: the grammar fuses a bare "ELSE" whose sole content is a nested
    # "IF" into one else_if_header node (see paragraphs.py:_parse_if_chain) —
    # so the reconstructed inner IF inherits that fused node's start (359,
    # the ELSE line), not the literal "IF APPL-EOF" line (360).
    assert (inner_if.ref.line_start, inner_if.ref.line_end) == (359, 361)
    assert [c.kind for c in inner_if.children] == ["MOVE"]

    assert (inner_else.ref.line_start, inner_else.ref.line_end) == (362, 366)
    assert [c.kind for c in inner_else.children] == ["OTHER", "MOVE", "PERFORM_CALL", "PERFORM_CALL"]
    perform_targets = [c.target for c in inner_else.children if c.kind == "PERFORM_CALL"]
    assert perform_targets == ["9910-DISPLAY-IO-STATUS", "9999-ABEND-PROGRAM"]


def test_evaluate_nesting_coactupc():
    """Assertion 3b: hand-verified EVALUATE, COACTUPC.cbl:2563-2641 (2000-DECIDE-ACTION).

    A nested EVALUATE at 2606-2615 sits inside the WHEN at 2602-2615, and
    PERFORM ... THRU targets are captured (9600-WRITE-PROCESSING THRU
    9600-WRITE-PROCESSING-EXIT at 2604-2605).
    """
    path = _find_program_file("COACTUPC")
    program = parse_program(path, backend="ast")
    para = next(p for p in program.paragraphs if p.span.name == "2000-DECIDE-ACTION")

    outer_evaluate = next(s for s in para.statements if s.kind == "EVALUATE")
    assert (outer_evaluate.ref.line_start, outer_evaluate.ref.line_end) == (2563, 2641)
    assert len(outer_evaluate.children) == 7
    assert all(c.kind == "WHEN" for c in outer_evaluate.children)

    when_2602 = next(w for w in outer_evaluate.children if w.ref.line_start == 2602)
    assert when_2602.ref.line_end == 2615
    perform_call, nested_evaluate = when_2602.children
    assert perform_call.kind == "PERFORM_CALL"
    assert (perform_call.target, perform_call.thru_target) == (
        "9600-WRITE-PROCESSING", "9600-WRITE-PROCESSING-EXIT",
    )
    assert nested_evaluate.kind == "EVALUATE"
    assert (nested_evaluate.ref.line_start, nested_evaluate.ref.line_end) == (2606, 2615)
    assert len(nested_evaluate.children) == 4
    assert all(c.kind == "WHEN" for c in nested_evaluate.children)


@pytest.mark.parametrize("name", GATE_PROGRAMS)
def test_preprocess_line_count_invariant(name):
    """Assertion 4: preprocess(src).text has identical line count, all 10."""
    path = _find_program_file(name)
    source = path.read_text(encoding="utf-8", errors="replace")
    pre = preprocess(source)
    assert len(pre.text.splitlines()) == len(source.splitlines())


def test_copybook_field_resolves_via_linemap():
    """Assertion 5: a copybook-expanded field resolves via LineMap to (copybook file, line).

    CVACT01Y (account record) is COPYed by several gate programs (e.g.
    CBACT01C.cbl:89); ACCT-CURR-BAL is declared at CVACT01Y.cpy:7.
    """
    src = "       COPY CVACT01Y.\n"
    exp = expand(src, SEARCH_PATHS)
    out_lines = exp.text.splitlines()
    expanded_line = next(i for i, line in enumerate(out_lines, start=1) if "ACCT-CURR-BAL" in line)

    entry = next(e for e in exp.line_map if e.expanded_start <= expanded_line <= e.expanded_end)
    assert entry.source_file.upper().endswith("CVACT01Y.CPY")
    original_line = entry.source_line_start + (expanded_line - entry.expanded_start)

    copybook_lines = (CARDDEMO / "app" / "cpy" / "CVACT01Y.cpy").read_text(errors="replace").splitlines()
    assert "ACCT-CURR-BAL" in copybook_lines[original_line - 1]


def _flatten(statements):
    for s in statements:
        yield s
        yield from _flatten(s.children)


def test_call_literal_taxonomy_cbact01c():
    """T1.2 D1: CALL 'literal' -> kind=CALL, target=program, dynamic=False."""
    program = parse_program(_find_program_file("CBACT01C"), backend="ast")
    calls = [s for s in _flatten(
        [st for p in program.paragraphs for st in p.statements]) if s.kind == "CALL"]
    by_line = {c.ref.line_start: c for c in calls}
    assert by_line[231].target == "COBDATFT" and by_line[231].dynamic is False
    assert by_line[410].target == "CEE3ABD" and by_line[410].dynamic is False


def test_goto_taxonomy_coactupc():
    """T1.2 D1: GO TO <label> -> kind=GOTO with target populated."""
    program = parse_program(_find_program_file("COACTUPC"), backend="ast")
    gotos = [s for s in _flatten(
        [st for p in program.paragraphs for st in p.statements]) if s.kind == "GOTO"]
    assert gotos, "COACTUPC has GO TO usage"
    first = min(gotos, key=lambda s: s.ref.line_start)
    assert (first.ref.line_start, first.target) == (973, "COMMON-RETURN")
    assert all(g.target for g in gotos)
