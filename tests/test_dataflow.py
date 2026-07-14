"""T1.3 gate: interprocedural def-use over CardDemo.

Golden fixtures tests/fixtures/dataflow/<name>.json hold the full VariableTrace
(sites: kind, statement_kind, program, paragraph, line span, excerpt) for 10
variables spanning 4 programs (COSGN00C, CBTRN02C, CBACT04C, COADM01C),
hand-verified against source. Coverage of the required cases:
- qualified `X OF Y`            -> errmsgo_of_cosgn0ao
- copybook-defined decl via LineMap -> cdemo_admin_opt_count, ws_curdate
- def/use in <preamble> driver  -> end_of_file (CBTRN02C)
- REDEFINES-flagged             -> ws_curdate
- 88-level -> parent field      -> ws_err_flg
- corpus-wide vs program-scoped -> acct_curr_bal (both asserted)
"""
import json
from pathlib import Path

import pytest

from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.static_analysis.dataflow import trace_variable

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"
CBL_DIR = CARDDEMO / "app" / "cbl"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "dataflow"

# (fixture_name, variable, [programs], scope)
GATE_SPEC = [
    ("ws_err_flg", "WS-ERR-FLG", ["COSGN00C"], "COSGN00C"),
    ("errmsgo_of_cosgn0ao", "ERRMSGO OF COSGN0AO", ["COSGN00C"], "COSGN00C"),
    ("end_of_file", "END-OF-FILE", ["CBTRN02C"], "CBTRN02C"),
    ("acct_curr_bal", "ACCT-CURR-BAL", ["CBACT04C", "CBTRN02C"], None),
    ("ws_curdate", "WS-CURDATE", ["COADM01C"], "COADM01C"),
    ("cdemo_admin_opt_count", "CDEMO-ADMIN-OPT-COUNT", ["COADM01C"], "COADM01C"),
    ("ws_monthly_int", "WS-MONTHLY-INT", ["CBACT04C"], "CBACT04C"),
    ("ws_total_int", "WS-TOTAL-INT", ["CBACT04C"], "CBACT04C"),
    ("dalytran_amt", "DALYTRAN-AMT", ["CBTRN02C"], "CBTRN02C"),
    ("ws_record_count", "WS-RECORD-COUNT", ["CBACT04C"], "CBACT04C"),
]

pytestmark = pytest.mark.skipif(
    not CARDDEMO.is_dir(), reason="corpora not fetched (run scripts/fetch_corpora.sh)",
)


def _load(programs):
    return [parse_program(CBL_DIR / f"{n}.cbl", include_preamble=True) for n in programs]


def _serialize(trace):
    return {
        "variable": trace.variable,
        "scoped_program": trace.scoped_program,
        "sites": [
            {
                "kind": s.kind,
                "statement_kind": s.statement_kind,
                "program": s.ref.program,
                "paragraph": s.ref.paragraph,
                "line_start": s.ref.line_start,
                "line_end": s.ref.line_end,
                "excerpt": s.excerpt,
            }
            for s in trace.sites
        ],
    }


@pytest.mark.parametrize("name,var,programs,scope", GATE_SPEC, ids=[s[0] for s in GATE_SPEC])
def test_trace_matches_fixture(name, var, programs, scope):
    fixture = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    trace = trace_variable(var, _load(programs), None, program=scope)
    assert _serialize(trace) == fixture


def test_qualified_resolves_to_specific_field():
    """ERRMSGO OF COSGN0AO resolves via the OF qualifier, not any bare ERRMSGO."""
    trace = trace_variable("ERRMSGO OF COSGN0AO", _load(["COSGN00C"]), None, program="COSGN00C")
    assert trace.sites
    assert all("?ambiguous" not in s.statement_kind for s in trace.sites)
    # The qualified target is the BMS map field; every site's excerpt names it.
    assert any("ERRMSGO OF COSGN0AO" in s.excerpt for s in trace.sites)


def test_qualified_trace_is_case_insensitive():
    """F5 (review 2026-07-12): COBOL names and the OF/IN keyword are
    case-insensitive — a lowercase spec must resolve to the same sites as the
    uppercase form, not silently return zero."""
    programs = _load(["COSGN00C"])
    upper = trace_variable("ERRMSGO OF COSGN0AO", programs, None, program="COSGN00C")
    lower = trace_variable("errmsgo of cosgn0ao", programs, None, program="COSGN00C")
    mixed = trace_variable("ErrMsgO In CoSgn0aO", programs, None, program="COSGN00C")

    assert upper.sites, "fixture precondition: the uppercase spec finds sites"
    assert _serialize(lower)["sites"] == _serialize(upper)["sites"]
    assert _serialize(mixed)["sites"] == _serialize(upper)["sites"]


def test_copybook_declaration_resolves_via_linemap():
    """CDEMO-ADMIN-OPT-COUNT's VALUE-clause def points into copybook COADM02Y."""
    trace = trace_variable("CDEMO-ADMIN-OPT-COUNT", _load(["COADM01C"]), None, program="COADM01C")
    decl = [s for s in trace.sites if s.statement_kind == "VALUE-clause"]
    assert len(decl) == 1
    assert decl[0].ref.program == "COADM02Y"  # the copybook, not the program
    assert "CDEMO-ADMIN-OPT-COUNT" in decl[0].excerpt


def test_preamble_sites_attributed():
    """END-OF-FILE is used in CBTRN02C's unnamed driver -> <preamble> paragraph."""
    trace = trace_variable("END-OF-FILE", _load(["CBTRN02C"]), None, program="CBTRN02C")
    assert any(s.ref.paragraph == "<preamble>" for s in trace.sites)


def test_redefines_alias_flagged():
    """WS-CURDATE is redefined by WS-CURDATE-N (CSDAT01Y) -> a REDEFINES-alias def."""
    trace = trace_variable("WS-CURDATE", _load(["COADM01C"]), None, program="COADM01C")
    alias = [s for s in trace.sites if s.statement_kind == "REDEFINES-alias"]
    assert alias
    assert alias[0].ref.program == "CSDAT01Y"
    assert "REDEFINES" in alias[0].excerpt.upper()


def test_88_level_maps_to_parent():
    """`IF NOT ERR-FLG-ON` and `SET ERR-FLG-OFF TO TRUE` are use/def of the
    parent WS-ERR-FLG; tracing the 88 name gives the same sites as the parent."""
    parent = trace_variable("WS-ERR-FLG", _load(["COSGN00C"]), None, program="COSGN00C")
    via_88 = trace_variable("ERR-FLG-ON", _load(["COSGN00C"]), None, program="COSGN00C")
    assert _serialize(parent)["sites"] == _serialize(via_88)["sites"]
    assert any(s.kind == "use" and "ERR-FLG-ON" in s.excerpt for s in parent.sites)
    assert any(s.kind == "def" and s.statement_kind == "SET" for s in parent.sites)


def test_corpus_wide_vs_scoped():
    """ACCT-CURR-BAL corpus-wide crosses CBACT04C + CBTRN02C; scoped to one
    program is a strict subset."""
    programs = _load(["CBACT04C", "CBTRN02C"])
    corpus = trace_variable("ACCT-CURR-BAL", programs, None, program=None)
    scoped = trace_variable("ACCT-CURR-BAL", programs, None, program="CBACT04C")

    corpus_programs = {s.ref.program for s in corpus.sites}
    assert {"CBACT04C", "CBTRN02C"} <= corpus_programs
    assert corpus.scoped_program is None and scoped.scoped_program == "CBACT04C"
    assert all(s.ref.program == "CBACT04C" for s in scoped.sites)
    assert len(scoped.sites) < len(corpus.sites)
