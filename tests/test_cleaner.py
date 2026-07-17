"""T1.1 gate: ingest/cleaner.py preprocessor unit tests."""
import pytest

from cobol_archaeologist.ingest.cleaner import PreprocessError, preprocess


def _lines(text: str) -> list[str]:
    return text.splitlines()


def test_line_count_preserved():
    src = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC CICS RETURN\n"
        "           END-EXEC.\n"
        "           GOBACK.\n"
    )
    result = preprocess(src)
    assert len(_lines(result.text)) == len(_lines(src))


def test_exec_cics_masked_single_line():
    src = (
        "       MAIN-PARA.\n"
        "           EXEC CICS RETURN END-EXEC.\n"
        "           GOBACK.\n"
    )
    result = preprocess(src)
    out = _lines(result.text)
    assert out[1].strip() == "CONTINUE."
    assert len(result.masked_spans) == 1
    span = result.masked_spans[0]
    assert span.kind == "exec_cics"
    assert span.start_line == span.end_line == 2
    assert "EXEC CICS RETURN END-EXEC." in span.original_text


def test_exec_sql_multiline_masked_with_period():
    src = (
        "       MAIN-PARA.\n"
        "           EXEC SQL\n"
        "               SELECT 1 INTO :WS-X FROM SYSIBM.SYSDUMMY1\n"
        "           END-EXEC.\n"
        "           GOBACK.\n"
    )
    result = preprocess(src)
    out = _lines(result.text)
    assert out[1].strip() == "CONTINUE"
    assert out[2].strip() == ""
    assert out[3].strip() == "CONTINUE."
    assert len(result.masked_spans) == 1
    span = result.masked_spans[0]
    assert span.kind == "exec_sql"
    assert (span.start_line, span.end_line) == (2, 4)
    assert "SELECT 1 INTO" in span.original_text


def test_exec_dli_without_terminal_period():
    src = (
        "       MAIN-PARA.\n"
        "           EXEC DLI GU\n"
        "           END-EXEC\n"
        "           DISPLAY 'X'.\n"
    )
    result = preprocess(src)
    out = _lines(result.text)
    assert out[1].strip() == "CONTINUE"
    assert out[2].strip() == ""
    assert result.masked_spans[0].kind == "exec_dli"


def test_comment_lines_never_scanned_for_exec_or_copy():
    src = (
        "      * EXEC CICS RETURN END-EXEC. this is commentary\n"
        "      / COPY FOO REPLACING ==A== BY ==B==.\n"
        "           DISPLAY 'X'.\n"
    )
    result = preprocess(src)
    assert result.masked_spans == []
    out = _lines(result.text)
    assert out[0] == src.splitlines()[0]
    assert out[1] == src.splitlines()[1]


def test_copy_replacing_masked_single_line():
    src = (
        "       MAIN-PARA.\n"
        "           COPY FOO REPLACING ==A== BY ==B==.\n"
        "           GOBACK.\n"
    )
    result = preprocess(src)
    out = _lines(result.text)
    assert out[1].strip() == "CONTINUE."
    span = result.masked_spans[0]
    assert span.kind == "copy_replacing"
    assert span.start_line == span.end_line == 2


def test_copy_replacing_multiline_masked():
    src = (
        "       MAIN-PARA.\n"
        "           COPY CSSETATY REPLACING\n"
        "             ==(TESTVAR1)== BY ==ACCT-STATUS==\n"
        "             ==(MAPNAME3)== BY ==CACTUPA== .\n"
        "           GOBACK.\n"
    )
    result = preprocess(src)
    out = _lines(result.text)
    assert out[1].strip() == ""
    assert out[2].strip() == ""
    assert out[3].strip() == "CONTINUE."
    span = result.masked_spans[0]
    assert span.kind == "copy_replacing"
    assert (span.start_line, span.end_line) == (2, 4)


def test_sequence_area_and_col_73_plus_ignored():
    # cols 1-6 sequence numbers + text past col 72 must not trigger scanning.
    src = (
        "123456           DISPLAY 'X'.                                    junk-past-72\n"
    )
    result = preprocess(src)
    assert result.masked_spans == []
    assert _lines(result.text)[0] == src.splitlines()[0]


def test_not_equal_glued_normalized():
    """Regression: T1.1 work-order rule register — CBACT04C.cbl:194 NOT= glued."""
    src = (
        "       MAIN-PARA.\n"
        "           IF TRANCAT-ACCT-ID NOT= WS-LAST-ACCT-NUM\n"
        "               DISPLAY 'X'\n"
        "           END-IF.\n"
    )
    result = preprocess(src)
    assert "NOT =" in _lines(result.text)[1]
    assert result.masked_spans == []
    assert len(_lines(result.text)) == len(_lines(src))


def test_continued_literal_spliced():
    """Regression: T1.1 work-order rule register — CBSTM03A.CBL:157-158 continuation."""
    src = (
        "       01  HTML-LINES.\n"
        "             88  HTML-L08 VALUE '<table  align=\"center\" frame=\"box\" styl\n"
        "      -             'e=\"width:70%; font:12px Segoe UI,sans-serif;\">'.\n"
        "             88  HTML-LTRS VALUE '<tr>'.\n"
    )
    result = preprocess(src)
    out = _lines(result.text)
    assert "HTML-L08" in out[1]
    assert out[1].rstrip().endswith("'.") or out[1].rstrip().endswith('".')
    assert out[2].strip() == ""
    assert len(out) == len(_lines(src))
    assert result.masked_spans == []


# -- F6 (review 2026-07-12): unterminated blocks at EOF must raise -----------

def test_unterminated_exec_raises():
    """An EXEC block with no END-EXEC before EOF is malformed input: raise,
    never emit blanked lines with no MaskedSpan to show for them."""
    src = (
        "       MAIN-PARA.\n"
        "           EXEC CICS SEND\n"
        "                MAP('X')\n"
    )
    with pytest.raises(PreprocessError) as exc:
        preprocess(src)
    assert exc.value.kind == "exec_cics"
    assert exc.value.start_line == 2


def test_unterminated_copy_replacing_raises():
    src = (
        "       01  WS-REC.\n"
        "           COPY CVACT01Y REPLACING ==:X:== BY ==ACCT==\n"
    )
    with pytest.raises(PreprocessError) as exc:
        preprocess(src)
    assert exc.value.kind == "copy_replacing"
    assert exc.value.start_line == 2


def test_terminated_blocks_still_pass():
    """The F6 guard must not fire on well-formed input (negative control)."""
    src = (
        "       MAIN-PARA.\n"
        "           EXEC CICS SEND\n"
        "                MAP('X')\n"
        "           END-EXEC.\n"
    )
    result = preprocess(src)
    assert len(result.masked_spans) == 1
    assert len(_lines(result.text)) == len(_lines(src))
