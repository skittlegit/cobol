"""T1.1 gate #5: parser/copybooks.py expansion + LineMap unit tests."""
from pathlib import Path

import pytest

from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.tool_types import LineMapEntry

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"
SEARCH_PATHS = [CARDDEMO / "app" / "cpy", CARDDEMO / "app" / "cpy-bms"]

pytestmark = pytest.mark.skipif(
    not CARDDEMO.is_dir(), reason="corpora not fetched (run scripts/fetch_corpora.sh)",
)


def test_plain_copy_resolves_and_inlines():
    src = (
        "       01  SOME-RECORD.\n"
        "       COPY CVACT01Y.\n"
        "       PROCEDURE DIVISION.\n"
    )
    exp = expand(src, SEARCH_PATHS)
    assert "ACCT-CURR-BAL" in exp.text
    assert any("CVACT01Y" in e.source_file for e in exp.line_map)


def test_linemap_round_trips_to_copybook_line():
    """Gate #5: a copybook-expanded field resolves via LineMap to (file, line)."""
    src = "       COPY CVACT01Y.\n"
    exp = expand(src, SEARCH_PATHS)
    out_lines = exp.text.splitlines()
    field_idx = next(i for i, line in enumerate(out_lines) if "ACCT-CURR-BAL" in line)
    expanded_line = field_idx + 1

    entry = next(e for e in exp.line_map if e.expanded_start <= expanded_line <= e.expanded_end)
    assert entry.source_file.upper().endswith("CVACT01Y.CPY")
    original_line = entry.source_line_start + (expanded_line - entry.expanded_start)

    copybook_text = (CARDDEMO / "app" / "cpy" / "CVACT01Y.cpy").read_text(errors="replace")
    assert "ACCT-CURR-BAL" in copybook_text.splitlines()[original_line - 1]


def test_own_lines_are_source_file_empty_string():
    src = "       DISPLAY 'X'.\n"
    exp = expand(src, SEARCH_PATHS)
    assert exp.line_map == [
        LineMapEntry(expanded_start=1, expanded_end=1, source_file="", source_line_start=1)
    ]


def test_quoted_copy_name_resolves():
    src = "       COPY 'CSUTLDWY'.\n"
    exp = expand(src, SEARCH_PATHS)
    assert any("CSUTLDWY" in e.source_file for e in exp.line_map)


def test_copy_replacing_pseudo_text_substitution():
    """Regression: COACTUPC.cbl:3208 CSSETATY REPLACING pseudo-text."""
    src = (
        "           COPY CSSETATY REPLACING\n"
        "             ==(TESTVAR1)== BY ==ACCT-STATUS==\n"
        "             ==(SCRNVAR2)== BY ==ACSTTUS==\n"
        "             ==(MAPNAME3)== BY ==CACTUPA== .\n"
    )
    exp = expand(src, SEARCH_PATHS)
    assert "FLG-ACCT-STATUS-NOT-OK" in exp.text
    assert "ACSTTUSC OF CACTUPAO" in exp.text
    assert "(TESTVAR1)" not in exp.text


def test_unresolved_copybook_passes_through_literally():
    """DFHAID/DFHBMSCA are CICS-supplied, not present in CardDemo's copybook dirs."""
    src = "       COPY DFHAID.\n       COPY DFHBMSCA.\n"
    exp = expand(src, SEARCH_PATHS)
    out = exp.text.splitlines()
    assert out[0].strip() == "COPY DFHAID."
    assert out[1].strip() == "COPY DFHBMSCA."
    assert all(e.source_file == "" for e in exp.line_map)


def test_line_map_covers_whole_output_contiguously():
    src = (
        "       01  SOME-RECORD.\n"
        "       COPY CVACT01Y.\n"
        "       COPY CODATECN.\n"
        "       PROCEDURE DIVISION.\n"
    )
    exp = expand(src, SEARCH_PATHS)
    total_lines = len(exp.text.splitlines())
    assert exp.line_map[0].expanded_start == 1
    assert exp.line_map[-1].expanded_end == total_lines
    for a, b in zip(exp.line_map, exp.line_map[1:]):
        assert b.expanded_start == a.expanded_end + 1
