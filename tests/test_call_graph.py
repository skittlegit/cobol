"""T1.2 gate: call-graph builder over 5 CardDemo programs.

Golden fixtures tests/fixtures/call_graph/<prog>.json hold each program's
adjacency (source paragraph -> sorted unique {program, paragraph, edge_kind}),
built from the graph and hand-verified against source:
- CBACT01C: batch preamble PERFORM roots + literal CALL edges.
- COSGN00C: XCTL to a loaded program (COADM01C.MAIN-PARA) and an unloaded one
  (COMEN01C, paragraph unknown).
- COACTUPC: PERFORM..THRU expansion (0000-MAIN) + GO TO COMMON-RETURN.
- COADM01C: dynamic XCTL PROGRAM(identifier) -> unresolved.
The synthetic tests/fixtures/synthetic/DEADEX.cbl proves the unreachable case
(no gate program has genuinely dead paragraphs).
"""
import json
from pathlib import Path

import pytest

from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.static_analysis.call_graph import build_call_graph
from cobol_archaeologist.tool_types import NodeRef

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"
CBL_DIR = CARDDEMO / "app" / "cbl"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "call_graph"
SYNTHETIC_DIR = REPO_ROOT / "tests" / "fixtures" / "synthetic"

GATE_PROGRAMS = ["CBACT01C", "CBTRN02C", "COSGN00C", "COADM01C", "COACTUPC"]

corpus_only = pytest.mark.skipif(
    not CARDDEMO.is_dir(), reason="corpora not fetched (run scripts/fetch_corpora.sh)",
)


@pytest.fixture(scope="module")
def graph():
    programs, pres = [], {}
    for name in GATE_PROGRAMS:
        path = CBL_DIR / f"{name}.cbl"
        program = parse_program(path, backend="ast", include_preamble=True)
        programs.append(program)
        pres[program.program_id] = preprocess(path.read_text(encoding="utf-8", errors="replace"))
    return build_call_graph(programs, pres)


def _adjacency(graph, program: str) -> dict:
    adj: dict[str, set] = {}
    for edge in graph.edges:
        if edge.source.program != program:
            continue
        adj.setdefault(edge.source.paragraph, set()).add(
            (edge.target.program, edge.target.paragraph, edge.edge_kind))
    return {
        src: [{"program": p, "paragraph": q, "edge_kind": k} for (p, q, k) in sorted(targets)]
        for src, targets in sorted(adj.items())
    }


# -- Gate 1: exact adjacency + the three required edge shapes ---------------

@corpus_only
@pytest.mark.parametrize("program", GATE_PROGRAMS)
def test_adjacency_matches_fixture(graph, program):
    expected = json.loads((FIXTURES_DIR / f"{program}.json").read_text(encoding="utf-8"))
    assert _adjacency(graph, program) == expected


@corpus_only
def test_thru_expansion_present(graph):
    """COACTUPC 0000-MAIN PERFORM 1000-PROCESS-INPUTS THRU ...-EXIT expands to
    both adjacent paragraphs (THRU is positional over Program.paragraphs)."""
    callees = {(n.program, n.paragraph) for n in graph.callees(
        NodeRef(program="COACTUPC", paragraph="0000-MAIN"))}
    assert ("COACTUPC", "1000-PROCESS-INPUTS") in callees
    assert ("COACTUPC", "1000-PROCESS-INPUTS-EXIT") in callees


@corpus_only
def test_goto_edge_present(graph):
    goto_edges = [e for e in graph.edges if e.edge_kind == "goto" and e.source.program == "COACTUPC"]
    assert goto_edges
    assert any(e.target.paragraph == "COMMON-RETURN" for e in goto_edges)


@corpus_only
def test_cross_program_xctl_edge_present(graph):
    """COSGN00C READ-USER-SEC-FILE XCTLs COADM01C ('literal') -> its first
    paragraph; and COMEN01C (not loaded) -> paragraph unknown ('')."""
    xctl = [e for e in graph.edges if e.edge_kind == "xctl" and e.source.program == "COSGN00C"]
    targets = {(e.target.program, e.target.paragraph) for e in xctl}
    assert ("COADM01C", "MAIN-PARA") in targets
    assert ("COMEN01C", "") in targets


# -- Gate 2: unresolved is complete (never silently dropped) ----------------

@corpus_only
def test_unresolved_counts(graph):
    dynamic_calls = [u for u in graph.unresolved if "dynamic CALL" in u.reason]
    dynamic_xctl = [u for u in graph.unresolved if "PROGRAM(identifier)" in u.reason]
    # All CALLs in the 5 programs are CALL 'literal' — zero dynamic CALLs.
    assert len(dynamic_calls) == 0
    # Three XCTL PROGRAM(ws-var): COADM01C x2, COACTUPC x1.
    assert len(dynamic_xctl) == 3
    dyn_sites = {(u.ref.program, u.ref.line_start) for u in dynamic_xctl}
    assert dyn_sites == {("COADM01C", 145), ("COADM01C", 168), ("COACTUPC", 956)}


@corpus_only
def test_perform_thru_unknown_endpoint_unresolved(graph):
    """COACTUPC PERFORMs copybook-provided paragraphs (YYYY-STORE-PFKEY,
    EDIT-DATE-*) via THRU; those aren't in the program AST, so they are
    recorded unresolved, not dropped."""
    thru_unknown = [u for u in graph.unresolved if "THRU" in u.reason and "unknown endpoint" in u.reason]
    assert len(thru_unknown) == 6


# -- Gate 3: reachability -----------------------------------------------------

@corpus_only
def test_reachability_marks_known_reachable(graph):
    reachable = graph.reachable_from(graph.entry_points("COACTUPC"))
    assert any(n.program == "COACTUPC" and n.paragraph == "9000-READ-ACCT" for n in reachable)


def test_synthetic_dead_code_unreachable():
    """Negative case: DEAD-A/DEAD-B form an unreferenced PERFORM cycle — each
    has an incoming edge (so neither is an entry point) yet neither is
    reachable from MAIN-PARA."""
    path = SYNTHETIC_DIR / "DEADEX.cbl"
    program = parse_program(path, backend="ast", include_preamble=True)
    graph = build_call_graph(
        [program], {program.program_id: preprocess(path.read_text(encoding="utf-8"))})

    entries = graph.entry_points("DEADEX")
    assert [e.paragraph for e in entries] == ["MAIN-PARA"]

    reachable = {(n.program, n.paragraph) for n in graph.reachable_from(entries)}
    all_nodes = {(n.program, n.paragraph) for n in graph.nodes_by_program["DEADEX"]}
    dead = all_nodes - reachable
    assert dead == {("DEADEX", "DEAD-A"), ("DEADEX", "DEAD-B")}


# -- callers/callees sanity ---------------------------------------------------

@corpus_only
def test_callers_and_callees_are_inverse(graph):
    node = NodeRef(program="COACTUPC", paragraph="9000-READ-ACCT")
    for callee in graph.callees(node):
        assert any(c.program == node.program and c.paragraph == node.paragraph
                   for c in graph.callers(callee))
