"""T1.4 gate ⛳ M1: backward program slicer over CardDemo.

Golden fixtures tests/fixtures/slices/<name>.json hold each slice's exact
ordered (program, line, text) statement set + paragraphs + is_interprocedural,
hand-verified against source. The 10 slices cover the required composition:
- interprocedural (cross-paragraph): tran_cat_bal, ws_temp_bal, cdemo_acct_id,
  ws_err_flg, cdemo_pgm_reenter, cdemo_from_tranid (6, ≥3);
- PERFORM chain depth ≥2: tran_cat_bal (preamble→2000→2700→2700-A/B),
  cdemo_acct_id (0000→2000→2200→2210 via THRU);
- copybook-declared root (copybook-stem ref present): cdemo_admin_opt_count
  (COADM02Y), cdemo_acct_id (CVCRD01Y);
- nested IF-inside-IF guard: cdemo_pgm_reenter (COTRN02C 115→120);
- EVALUATE/WHEN guard: ws_err_flg (COSGN00C);
- <preamble> statements: tran_cat_bal, ws_temp_bal (CBTRN02C driver);
- VALUE-clause decl pulled (D4): cdemo_admin_opt_count, ws_option, ws_err_flg;
- deliberately trivial (single paragraph, ≤4 stmts): ws_monthly_int (1),
  ws_create_trancat_rec (3), ws_option (3).
- cross-program corpus-wide (program=None): cdemo_from_tranid.
"""
import json
from pathlib import Path

import pytest

from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.static_analysis.call_graph import build_call_graph
from cobol_archaeologist.static_analysis.slicer import slice_on

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"
CBL_DIR = CARDDEMO / "app" / "cbl"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "slices"

# (fixture_name, variable, [programs], scope)
GATE_SPEC = [
    ("ws_monthly_int", "WS-MONTHLY-INT", ["CBACT04C"], "CBACT04C"),
    ("ws_create_trancat_rec", "WS-CREATE-TRANCAT-REC", ["CBTRN02C"], "CBTRN02C"),
    ("ws_option", "WS-OPTION", ["COADM01C"], "COADM01C"),
    ("cdemo_admin_opt_count", "CDEMO-ADMIN-OPT-COUNT", ["COADM01C"], "COADM01C"),
    ("tran_cat_bal", "TRAN-CAT-BAL", ["CBTRN02C"], "CBTRN02C"),
    ("ws_temp_bal", "WS-TEMP-BAL", ["CBTRN02C"], "CBTRN02C"),
    ("cdemo_acct_id", "CDEMO-ACCT-ID", ["COACTVWC"], "COACTVWC"),
    ("ws_err_flg", "WS-ERR-FLG", ["COSGN00C"], "COSGN00C"),
    ("cdemo_pgm_reenter", "CDEMO-PGM-REENTER", ["COTRN02C"], "COTRN02C"),
    ("cdemo_from_tranid", "CDEMO-FROM-TRANID", ["COTRN02C", "COACTVWC"], None),
]

pytestmark = pytest.mark.skipif(
    not CARDDEMO.is_dir(), reason="corpora not fetched (run scripts/fetch_corpora.sh)",
)

_cache: dict = {}


def _load(programs):
    key = tuple(programs)
    if key not in _cache:
        progs = [parse_program(CBL_DIR / f"{n}.cbl", include_preamble=True) for n in programs]
        pres = {p.program_id: preprocess(Path(p.path).read_text(encoding="utf-8", errors="replace"))
                for p in progs}
        _cache[key] = (progs, build_call_graph(progs, pres))
    return _cache[key]


def _serialize(sl):
    return {
        "variable": sl.variable,
        "scoped_program": sl.scoped_program,
        "is_interprocedural": sl.is_interprocedural,
        "paragraphs": [{"program": p.program, "paragraph": p.paragraph} for p in sl.paragraphs],
        "statements": [
            {"program": s.ref.program, "paragraph": s.ref.paragraph,
             "line_start": s.ref.line_start, "line_end": s.ref.line_end, "text": s.text}
            for s in sl.statements
        ],
    }


def _run(var, programs, scope):
    progs, cg = _load(programs)
    return slice_on(var, progs, cg, program=scope)


@pytest.mark.parametrize("name,var,programs,scope", GATE_SPEC, ids=[s[0] for s in GATE_SPEC])
def test_slice_matches_fixture(name, var, programs, scope):
    fixture = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert _serialize(_run(var, programs, scope)) == fixture


def test_trivial_slice_does_not_over_include():
    """WS-MONTHLY-INT is a single unguarded COMPUTE with no in-program def of
    its inputs — the slice is exactly that one statement (no over-inclusion)."""
    sl = _run("WS-MONTHLY-INT", ["CBACT04C"], "CBACT04C")
    assert len(sl.statements) == 1
    assert sl.is_interprocedural is False
    assert sl.statements[0].ref.line_start == 464


def test_interprocedural_flag_and_perform_chain():
    """TRAN-CAT-BAL crosses paragraphs linked by a depth-3 PERFORM chain
    (<preamble> → 2000-POST-TRANSACTION → 2700-UPDATE-TCATBAL → 2700-A/B)."""
    sl = _run("TRAN-CAT-BAL", ["CBTRN02C"], "CBTRN02C")
    assert sl.is_interprocedural is True
    paras = {p.paragraph for p in sl.paragraphs}
    assert {"<preamble>", "2000-POST-TRANSACTION", "2700-UPDATE-TCATBAL"} <= paras
    # The connecting PERFORMs are present (glue).
    texts = " ".join(s.text for s in sl.statements)
    assert "PERFORM 2000-POST-TRANSACTION" in texts
    assert "PERFORM 2700-UPDATE-TCATBAL" in texts


def test_copybook_declared_root_in_slice():
    """cdemo_admin_opt_count pulls its VALUE-clause decl from copybook COADM02Y
    (a copybook-stem program ref appears in the slice)."""
    sl = _run("CDEMO-ADMIN-OPT-COUNT", ["COADM01C"], "COADM01C")
    assert any(s.ref.program == "COADM02Y" for s in sl.statements)


def test_nested_if_inside_if_guard():
    """CDEMO-PGM-REENTER's def (SET, line 121) is guarded by a nested
    IF-inside-IF (115 IF EIBCALEN=0 → its ELSE → 120 IF NOT CDEMO-PGM-REENTER),
    and the 88-level guard resolves to the parent CDEMO-PGM-CONTEXT."""
    sl = _run("CDEMO-PGM-REENTER", ["COTRN02C"], "COTRN02C")
    lines = {s.ref.line_start for s in sl.statements}
    assert {115, 120, 121} <= lines  # outer IF, inner IF, the guarded SET
    assert sl.is_interprocedural is True


def test_evaluate_when_guard():
    """WS-ERR-FLG's defs sit under EVALUATE/WHEN branches, which are pulled in."""
    sl = _run("WS-ERR-FLG", ["COSGN00C"], "COSGN00C")
    assert any(s.text.startswith("EVALUATE") for s in sl.statements)
    assert any(s.text.startswith("WHEN") for s in sl.statements)


def test_preamble_statements_included():
    sl = _run("WS-TEMP-BAL", ["CBTRN02C"], "CBTRN02C")
    assert any(p.paragraph == "<preamble>" for p in sl.paragraphs)


def test_corpus_wide_spans_two_programs():
    """CDEMO-FROM-TRANID corpus-wide (program=None) crosses COTRN02C + COACTVWC."""
    sl = _run("CDEMO-FROM-TRANID", ["COTRN02C", "COACTVWC"], None)
    assert sl.scoped_program is None
    assert sl.is_interprocedural is True
    assert {s.ref.program for s in sl.statements} >= {"COTRN02C", "COACTVWC"}


def test_statements_sorted_by_program_then_line():
    sl = _run("CDEMO-FROM-TRANID", ["COTRN02C", "COACTVWC"], None)
    keys = [(s.ref.program, s.ref.line_start, s.ref.line_end) for s in sl.statements]
    assert keys == sorted(keys)
