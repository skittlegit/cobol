"""T1.6 gate: RealToolLayer — the agent-facing facade over T1.1-T1.5.

Structural conformance (isinstance against the runtime-checkable ToolLayer
Protocol) is the contract's own stub-parity clause (CONTRACT.md Part 1); the
rest of this file pins the semantics Track C will consume, against CardDemo.

Skips without the corpus (and, for run_cobol, without cobc), same pattern as
the T1.1-T1.5 gates.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cobol_archaeologist import tool_types
from cobol_archaeologist.tool_types import CODE_CAP_LINES
from cobol_archaeologist.tools import GREP_CAP_MATCHES, RealToolLayer, ToolLookupError

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"
CBL_DIR = CARDDEMO / "app" / "cbl"
CPY_DIRS = [CARDDEMO / "app" / "cpy", CARDDEMO / "app" / "cpy-bms"]
SMOKE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "smoke" / "acct_curr_bal.json"

_HAVE_COBC = bool(os.environ.get("COBC") or shutil.which("cobc"))
needs_cobc = pytest.mark.skipif(
    not _HAVE_COBC, reason="cobc not found (run scripts/setup_cobc.sh)"
)

pytestmark = pytest.mark.skipif(
    not CARDDEMO.is_dir(),
    reason="corpora not fetched (run scripts/fetch_corpora.sh)",
)

# A 451-line paragraph (COACTUPC.cbl:2986-3436) — the cap fixture.
LONG_PARA = ("COACTUPC", "3300-SETUP-SCREEN-ATTRS", 2986, 3436)


@pytest.fixture(scope="module")
def layer():
    return RealToolLayer(corpus_root=CBL_DIR, copybook_paths=CPY_DIRS)


# -- Gate 1: structural conformance -----------------------------------------


def test_is_a_toollayer(layer):
    """The stub-parity clause: Track C's Week-7 seam test is a constructor swap
    of StubToolLayer for this, and nothing else may need to change."""
    assert isinstance(layer, tool_types.ToolLayer)


def test_empty_corpus_root_is_loud(tmp_path):
    """A corpus_root with no program sources fails at construction, rather than
    yielding a layer whose every lookup mysteriously misses."""
    with pytest.raises(ValueError, match="no COBOL program sources"):
        RealToolLayer(corpus_root=tmp_path, copybook_paths=[])


# -- Gate 2: read_paragraph / read_program ----------------------------------


def test_read_paragraph_returns_code_span_and_edges(layer):
    view = layer.read_paragraph("CBTRN02C", "2800-UPDATE-ACCOUNT-REC")

    assert isinstance(view, tool_types.ParagraphView)
    assert view.name == "2800-UPDATE-ACCOUNT-REC"
    assert view.ref.program == "CBTRN02C"
    assert view.ref.paragraph == "2800-UPDATE-ACCOUNT-REC"
    assert view.truncated is False
    # Code is the ORIGINAL source text of that span (CLAUDE.md rule 4).
    original = (
        (CBL_DIR / "CBTRN02C.cbl")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines()
    )
    assert view.code.splitlines() == [
        ln.rstrip() for ln in original[view.ref.line_start - 1 : view.ref.line_end]
    ]
    assert "ACCT-CURR-BAL" in view.code
    assert (
        tool_types.NodeRef(program="CBTRN02C", paragraph="2000-POST-TRANSACTION")
        in view.callers
    )


def test_read_paragraph_caps_long_code(layer):
    """Cap enforced: a >60-line paragraph returns exactly CODE_CAP_LINES lines,
    truncated=True, and a ref spanning the WHOLE paragraph so the consumer can
    fetch the rest."""
    program, name, start, end = LONG_PARA
    view = layer.read_paragraph(program, name)

    assert end - start + 1 > CODE_CAP_LINES  # fixture precondition
    assert view.truncated is True
    assert len(view.code.splitlines()) == CODE_CAP_LINES
    assert view.ref.line_start == start and view.ref.line_end == end


def test_read_paragraph_accepts_the_preamble_sentinel(layer):
    """`<preamble>` is a synthetic paragraph (the batch main driver), and is a
    first-class, readable node — CBACT04C's driver PERFORMs live there."""
    view = layer.read_paragraph("CBACT04C", "<preamble>")
    assert view.name == "<preamble>"
    assert view.callees


def test_read_program_is_spans_only(layer):
    view = layer.read_program("CBACT04C")

    assert isinstance(view, tool_types.ProgramView)
    assert view.program == "CBACT04C"
    assert Path(view.path).name == "CBACT04C.cbl"
    names = [p.name for p in view.paragraphs]
    assert "1050-UPDATE-ACCOUNT" in names
    assert all(p.line_end >= p.line_start for p in view.paragraphs)
    # No code dump: the model carries names + spans only.
    assert not hasattr(view.paragraphs[0], "code")


def test_unknown_lookups_raise(layer):
    with pytest.raises(ToolLookupError):
        layer.read_program("NOSUCHPROG")
    with pytest.raises(ToolLookupError):
        layer.read_paragraph("CBACT04C", "NO-SUCH-PARAGRAPH")
    with pytest.raises(ToolLookupError):
        layer.get_data_layout("NO-SUCH-RECORD")
    with pytest.raises(ToolLookupError):
        layer.resolve_copybook("NOSUCHBOOK")


# -- Gate 2: find_callers / find_callees ------------------------------------


def test_find_callers_and_callees(layer):
    callers = layer.find_callers("CBTRN02C", "2800-UPDATE-ACCOUNT-REC")
    assert callers == [
        tool_types.NodeRef(program="CBTRN02C", paragraph="2000-POST-TRANSACTION")
    ]

    callees = layer.find_callees("CBTRN02C", "2000-POST-TRANSACTION")
    assert (
        tool_types.NodeRef(program="CBTRN02C", paragraph="2800-UPDATE-ACCOUNT-REC")
        in callees
    )


def test_cross_program_edge_carries_empty_paragraph(layer):
    """A CALL/LINK/XCTL into a program outside the parsed set is still a real
    edge, with paragraph="" = 'program entry, first paragraph unknown'."""
    callees = layer.find_callees("COSGN00C", "SEND-SIGNON-SCREEN")
    programs = {c.program for c in callees}
    assert programs  # the paragraph transfers control somewhere
    assert all(isinstance(c, tool_types.NodeRef) for c in callees)


# -- Gate 2: trace_variable / slice_on --------------------------------------


def test_trace_variable_corpus_wide_and_scoped(layer):
    corpus = layer.trace_variable("ACCT-CURR-BAL")
    scoped = layer.trace_variable("ACCT-CURR-BAL", program="CBACT04C")

    assert isinstance(corpus, tool_types.VariableTrace)
    assert corpus.scoped_program is None and scoped.scoped_program == "CBACT04C"
    assert {s.ref.program for s in corpus.sites} >= {"CBACT04C", "CBTRN02C", "COBIL00C"}
    assert all(s.ref.program == "CBACT04C" for s in scoped.sites)
    assert len(scoped.sites) < len(corpus.sites)


def test_slice_on_is_interprocedural(layer):
    sl = layer.slice_on("ACCT-CURR-BAL", program="CBACT04C")

    assert isinstance(sl, tool_types.Slice)
    assert sl.scoped_program == "CBACT04C"
    assert sl.statements
    assert sl.is_interprocedural is True  # spans >1 paragraph
    assert len({p.paragraph for p in sl.paragraphs}) > 1
    # Every statement points at original source, in order.
    lines = [s.ref.line_start for s in sl.statements]
    assert lines == sorted(lines)


# -- Gate 2: resolve_copybook ------------------------------------------------


def test_resolve_copybook_text_and_linemap(layer):
    exp = layer.resolve_copybook("CVACT01Y")

    assert isinstance(exp, tool_types.CopybookExpansion)
    assert exp.name == "CVACT01Y"
    assert "ACCOUNT-RECORD" in exp.text
    assert "ACCT-CURR-BAL" in exp.text
    assert exp.truncated is False
    assert exp.line_map
    # The LineMap names a real file (never the "" self-reference of the raw
    # expander), so a consumer can resolve any line back to its origin.
    assert all(e.source_file for e in exp.line_map)
    assert any(Path(e.source_file).stem.upper() == "CVACT01Y" for e in exp.line_map)


# -- Gate 4: get_data_layout -------------------------------------------------


def test_get_data_layout_account_record(layer):
    """ACCOUNT-RECORD is declared in copybook CVACT01Y, not in any program: the
    field tree comes from the AST, and `source` is the LineMap-resolved
    ORIGINAL declaration site (the copybook, lines 4-17)."""
    layout = layer.get_data_layout("ACCOUNT-RECORD")

    assert isinstance(layout, tool_types.DataLayout)
    assert layout.record == "ACCOUNT-RECORD"
    assert layout.root.name == "ACCOUNT-RECORD"
    assert layout.root.level == 1

    # Declaration source resolves through the copybook LineMap, not the program.
    assert layout.source.program == "CVACT01Y"
    assert layout.source.line_start == 4
    assert layout.source.line_end == 17  # 01 line through the trailing FILLER

    children = {c.name: c for c in layout.root.children}
    assert children["ACCT-CURR-BAL"].pic == "S9(10)V99"
    assert children["ACCT-CURR-BAL"].level == 5
    assert children["ACCT-ID"].pic == "9(11)"
    assert [c.name for c in layout.root.children][-1] == "FILLER"
    assert len(layout.root.children) == 13


def test_get_data_layout_value_text_is_read_from_original(layer):
    """The preprocessor's continued-literal splice rewrites CBSTM03A:157-158 to
    a placeholder (`VALUE 'X'`) in the parse buffer. Structure must come from
    that buffer (it is what parses cleanly), but VALUE text must NEVER be taken
    from it — `source` resolves to the ORIGINAL lines, where the real literal
    lives. Reading preprocessed VALUEs would corrupt D4 evidence.
    """
    layout = layer.get_data_layout("HTML-LINES")
    assert layout.source.program == "CBSTM03A"

    original = (
        (CBL_DIR / "CBSTM03A.CBL")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines()
    )
    declared = "\n".join(
        original[layout.source.line_start - 1 : layout.source.line_end]
    )

    # The multi-line VALUE reads correctly from the original source...
    assert 'frame="box"' in declared
    assert "font:12px Segoe UI,sans-serif" in declared  # the CONTINUED half
    # ...and the parse-buffer placeholder never leaks into the returned span.
    assert "VALUE 'X'." not in declared

    # Structure survives the continued literal: the 88s declared AFTER it are
    # all present (an un-preprocessed parse ERRORs out and loses them). They
    # hang off the 05 they qualify, not off the record root — an 88 condition
    # name is a child of its field.
    fixed = next(c for c in layout.root.children if c.name == "HTML-FIXED-LN")
    assert fixed.level == 5 and fixed.pic == "X(100)"
    conditions = {c.name: c for c in fixed.children}
    assert {"HTML-L08", "HTML-LTRS", "HTML-L10"} <= set(conditions)
    assert conditions["HTML-L08"].level == 88
    assert conditions["HTML-L08"].pic is None  # a condition name has no PICTURE


# -- Gate 2: grep ------------------------------------------------------------


def test_grep_returns_pointers_and_caps(layer):
    result = layer.grep(r"ACCT-CURR-BAL")

    assert isinstance(result, tool_types.GrepResult)
    assert result.pattern == "ACCT-CURR-BAL"
    assert result.matches
    assert {m.program for m in result.matches} >= {"CBACT04C", "CBTRN02C"}
    # Line numbers are original-source and the text is that line.
    hit = next(m for m in result.matches if m.program == "CBACT04C")
    original = (
        (CBL_DIR / "CBACT04C.cbl")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines()
    )
    assert "ACCT-CURR-BAL" in original[hit.line - 1]
    assert hit.text.strip() == original[hit.line - 1].strip()


def test_grep_cap_enforced(layer):
    """A pattern matching most lines of the corpus is capped, not dumped."""
    result = layer.grep(r".")
    assert result.truncated is True
    assert len(result.matches) == GREP_CAP_MATCHES


def test_grep_searches_copybooks_too(layer):
    """Record layouts (and their VALUEs — the D4 evidence) live in copybooks,
    so grep spans them; a copybook hit reports its stem as `program`."""
    result = layer.grep(r"ACCT-CURR-BAL\s+PIC")
    assert any(m.program == "CVACT01Y" for m in result.matches)


# -- Gate 2: run_cobol -------------------------------------------------------


@needs_cobc
def test_run_cobol_wraps_a_bare_snippet(layer):
    result = layer.run_cobol("DISPLAY 'FROM-SNIPPET'.")
    assert isinstance(result, tool_types.RunResult)
    assert result.compiled_ok is True
    assert "FROM-SNIPPET" in result.stdout


@needs_cobc
def test_run_cobol_passes_a_full_program_through(layer):
    program = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FULLPROG.
       PROCEDURE DIVISION.
           DISPLAY 'FROM-FULL-PROGRAM'.
           STOP RUN.
"""
    result = layer.run_cobol(program)
    assert result.compiled_ok is True
    assert "FROM-FULL-PROGRAM" in result.stdout


@needs_cobc
def test_run_cobol_compile_failure_returns_result_never_raises(layer):
    """CICS source cannot compile under cobc — that is compiled_ok=False
    ('Tier-1 verification unavailable'), not an error."""
    source = (CBL_DIR / "COSGN00C.cbl").read_text(encoding="utf-8", errors="replace")
    result = layer.run_cobol(source)
    assert result.compiled_ok is False
    assert result.stderr.strip()


@needs_cobc
def test_run_cobol_accepts_stdin(layer):
    """RunInputs plumbs through the facade. Storage is declared by the caller:
    the bare-snippet shell invents no WORKING-STORAGE, so anything needing a
    variable is passed as a full program."""
    program = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ECHOIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-IN PIC X(16).
       PROCEDURE DIVISION.
           ACCEPT WS-IN.
           DISPLAY 'GOT:' WS-IN.
           STOP RUN.
"""
    result = layer.run_cobol(program, tool_types.RunInputs(stdin="PINGED\n"))
    assert result.compiled_ok is True, result.stderr
    assert "GOT:PINGED" in result.stdout


# -- Gate 2: search_regulations (typed stub, Track C owns) -------------------


def test_search_regulations_is_a_typed_stub(layer):
    with pytest.raises(NotImplementedError, match="Track C"):
        layer.search_regulations("credit card interest")


# -- Gate 3: the smoke script answers a real question via ToolLayer only -----


def test_smoke_script_matches_fixture():
    """scripts/smoke_tools.py answers 'which paragraphs write ACCT-CURR-BAL and
    who calls them?' using ONLY ToolLayer calls. Its output is this fixture."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "smoke_tools.py")],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == json.loads(
        SMOKE_FIXTURE.read_text(encoding="utf-8")
    )


if __name__ == "__main__":  # convenience: `python tests/test_tools.py`
    sys.exit(pytest.main([__file__, "-v"]))
