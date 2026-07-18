"""T1.5 gate: GnuCOBOL run harness (compile_check + run_cobol).

Skip-marked when ``cobc`` is absent (via COBC env or PATH), so the suite stays
green on machines without GnuCOBOL — same pattern as the corpora skip.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cobol_archaeologist.model.run_cobol import (
    CompileResult,
    _collect_output_files,
    compile_check,
    run_cobol,
    run_cobol_with_files,
)
from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.tool_types import RunInputs, RunResult

REPO_ROOT = Path(__file__).resolve().parents[1]
CARDDEMO = REPO_ROOT / "data" / "corpora" / "carddemo"

_HAVE_COBC = bool(os.environ.get("COBC") or shutil.which("cobc"))
needs_cobc = pytest.mark.skipif(
    not _HAVE_COBC, reason="cobc not found (run scripts/setup_cobc.sh)"
)
needs_corpus = pytest.mark.skipif(not CARDDEMO.is_dir(), reason="corpora not fetched")

TRIVIAL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TRIVIAL.
       PROCEDURE DIVISION.
           DISPLAY 'HELLO-FROM-COBC'.
           STOP RUN.
"""

INFINITE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOOPER.
       PROCEDURE DIVISION.
           PERFORM UNTIL 1 = 2
               CONTINUE
           END-PERFORM.
           STOP RUN.
"""

BROKEN = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BROKEN.
       PROCEDURE DIVISION.
           MOVE TO X.
"""


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError):
        return False
    return True


# 1. Trivial program compiles and runs; stdout asserted.
@needs_cobc
def test_trivial_program_runs():
    result = run_cobol(TRIVIAL)
    assert result.compiled_ok is True
    assert result.timed_out is False
    assert result.exit_code == 0
    assert "HELLO-FROM-COBC" in result.stdout


@needs_cobc
def test_stdin_is_delivered():
    program = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ECHOIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 LINE-IN PIC X(16).
       PROCEDURE DIVISION.
           ACCEPT LINE-IN.
           DISPLAY 'GOT:' LINE-IN.
           STOP RUN.
"""
    result = run_cobol(program, RunInputs(stdin="PINGVALUE\n"))
    assert result.compiled_ok is True
    assert "GOT:PINGVALUE" in result.stdout


# 2. Real CardDemo batch program (CBACT04C): compile-only via the syntax
#    oracle. CBACT04C declares PROCEDURE DIVISION USING EXTERNAL-PARMS (a
#    JCL-called subprogram), so `cobc -x` (standalone executable) cannot link
#    it — the work order's allowed fallback is a compile-only assertion. Its
#    COPY statements are expanded with the T1.1 expander so the source is
#    self-contained for the source-only compile_check signature.
@needs_cobc
@needs_corpus
def test_carddemo_batch_program_compiles():
    source = (CARDDEMO / "app" / "cbl" / "CBACT04C.cbl").read_text(
        encoding="utf-8", errors="replace"
    )
    search = [CARDDEMO / "app" / "cpy", CARDDEMO / "app" / "cpy-bms"]
    expanded = expand(source, search).text
    result = compile_check(expanded)
    assert result.ok is True, result.messages


# 3. Timeout: infinite loop -> timed_out in ~5s, no zombie.
@needs_cobc
def test_infinite_loop_times_out_and_is_reaped():
    start = time.monotonic()
    result = run_cobol(INFINITE)
    elapsed = time.monotonic() - start
    assert result.compiled_ok is True
    assert result.timed_out is True
    assert result.exit_code is None
    assert elapsed < 15  # killed near the 5s cap, not hung
    assert not _pid_alive(run_cobol.last_pid)  # child process is gone


# 4. CICS negative case: COSGN00C -> compiled_ok=False, stderr non-empty, no raise.
@needs_cobc
@needs_corpus
def test_cics_program_fails_to_compile_without_raising():
    source = (CARDDEMO / "app" / "cbl" / "COSGN00C.cbl").read_text(
        encoding="utf-8", errors="replace"
    )
    result = run_cobol(source)
    assert isinstance(result, RunResult)
    assert result.compiled_ok is False
    assert result.stderr.strip() != ""


# 5. compile_check on a broken program -> ok=False with a file:line message.
@needs_cobc
def test_compile_check_reports_broken_source():
    result = compile_check(BROKEN)
    assert isinstance(result, CompileResult)
    assert result.ok is False
    assert result.messages
    assert any(":" in m and "error" in m.lower() for m in result.messages)
    # Temp path is stripped; message anchors to the source file basename.
    assert all("cobc_syn_" not in m for m in result.messages)


@needs_cobc
def test_compile_check_accepts_valid_source():
    result = compile_check(TRIVIAL)
    assert result.ok is True
    assert result.messages == []


@needs_cobc
def test_run_cobol_with_files_captures_outputs():
    program = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. WRITER.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT OUTF ASSIGN TO 'out.txt'
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD OUTF.
       01 OREC PIC X(5).
       PROCEDURE DIVISION.
           OPEN OUTPUT OUTF.
           MOVE 'HELLO' TO OREC.
           WRITE OREC.
           CLOSE OUTF.
           STOP RUN.
"""
    result, outputs = run_cobol_with_files(program)
    assert result.compiled_ok is True
    assert "out.txt" in outputs
    assert outputs["out.txt"].strip() == "HELLO"


@pytest.mark.parametrize(
    "name",
    [
        "../escape.txt",
        "nested/../../escape.txt",
        "/absolute.txt",
        r"C:\absolute.txt",
        r"\\server\share\escape.txt",
    ],
)
def test_input_files_cannot_escape_the_run_directory(tmp_path, name):
    outside = tmp_path / "escape.txt"
    with pytest.raises(ValueError, match="relative path"):
        run_cobol_with_files(TRIVIAL, RunInputs(files={name: "owned"}))
    assert not outside.exists()


def test_output_collection_is_bounded_and_skips_links(tmp_path, monkeypatch):
    import cobol_archaeologist.model.run_cobol as mod

    monkeypatch.setattr(mod, "_OUTPUT_FILE_LIMIT", 2)
    monkeypatch.setattr(mod, "_OUTPUT_TOTAL_CAP", 7)
    monkeypatch.setattr(mod, "_OUTPUT_FILE_CAP", 5)
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text("123456789", encoding="utf-8")
    try:
        (tmp_path / "outside-link.txt").symlink_to(tmp_path.parent / "secret.txt")
    except OSError:
        pass  # Windows may deny unprivileged symlink creation.

    outputs = _collect_output_files(tmp_path, seeded=set())

    assert len(outputs) <= 2
    assert sum(len(value.encode("utf-8")) for value in outputs.values()) <= 7
    assert "outside-link.txt" not in outputs


# 6. Missing cobc is an error (RuntimeError), unlike a compile failure.
def test_missing_cobc_raises(monkeypatch):
    monkeypatch.delenv("COBC", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="cobc"):
        compile_check(TRIVIAL)


def test_module_importable_without_cobc():
    """The module and its types import cleanly even where cobc is absent."""
    import cobol_archaeologist.model.run_cobol as mod  # noqa: F401

    assert "run_cobol" in dir(mod) and "compile_check" in dir(mod)


if __name__ == "__main__":  # convenience: `python tests/test_run_cobol.py`
    sys.exit(pytest.main([__file__, "-v"]))
