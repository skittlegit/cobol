"""GnuCOBOL compile/behavior oracle harness (Track A, T1.5).

Two entry points over a sandboxed ``cobc`` invocation:

- :func:`compile_check` — the cheap syntax oracle Track B's T2.2 mutation
  pipeline calls on every generated instance (``cobc -fsyntax-only``).
- :func:`run_cobol` — compile-and-execute for GnuCOBOL-compilable COBOL,
  returning the frozen :class:`~cobol_archaeologist.tool_types.RunResult`.
  :func:`run_cobol_with_files` additionally returns files the program wrote.

``cobc`` is the compile/behavior oracle only, never the parser (CLAUDE.md
locked decision #3): CICS programs failing to compile here is expected, and is
reported as ``compiled_ok=False`` ("Tier-1 verification unavailable"), never an
exception. A missing ``cobc`` binary, by contrast, IS an error (RuntimeError).

Sandboxing is temp-dir + wall-clock timeout + a minimal subprocess environment
(only ``cobc``'s own directory on PATH, plus carried-through ``COB_*`` config
knobs). No network is used or needed.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

from cobol_archaeologist.tool_types import RunInputs, RunResult

_STD = "ibm"                       # cobc -std; CLAUDE.md pins the IBM dialect.
_RUN_TIMEOUT_S = 5.0
_OUTPUT_CAP = 64 * 1024            # per-stream capture cap (bytes)
_SRC_NAME = "prog.cbl"
_EXE_NAME = "prog"

# cobc diagnostic line: "<file>:<line>: error: <text>" (line part optional).
_DIAG_RE = re.compile(r"^(?P<file>[^:]+):(?:(?P<line>\d+):)?\s*(?P<kind>error|warning):\s*(?P<text>.*)$")

_INSTALL_HINT = (
    "cobc (GnuCOBOL) not found on PATH; run scripts/setup_cobc.sh "
    "(apt-get install -y gnucobol3) or set the COBC environment variable"
)


class CompileResult(BaseModel):
    """Result of the syntax oracle. NOT a tool_types contract shape — a Track
    A/B internal (import from ``model.run_cobol``)."""

    ok: bool
    messages: list[str]


# --------------------------------------------------------------------------
# cobc discovery + sandboxed environment
# --------------------------------------------------------------------------

def _find_cobc() -> str:
    cobc = os.environ.get("COBC") or shutil.which("cobc")
    if not cobc:
        raise RuntimeError(_INSTALL_HINT)
    return cobc


def _baseline_path(cobc_dir: str) -> str:
    """cobc's own directory (siblings: the C compiler + libcob) ahead of the
    OS baseline. The baseline is the platform's system directories, NOT the
    user's inherited PATH — cobc shells out to gcc/as/ld, which on Windows load
    system DLLs from System32. This is the OS floor, not a 'PATH surprise'."""
    parts = [cobc_dir]
    if os.name == "nt":
        sysroot = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"
        parts += [os.path.join(sysroot, "System32"), sysroot,
                  os.path.join(sysroot, "System32", "Wbem")]
    else:
        parts.append(os.defpath)
    return os.pathsep.join(p for p in parts if p)


def _derive_config_dir(cobc_dir: Path) -> str | None:
    """cobc's config directory, relative to its install prefix
    (``<prefix>/share/gnucobol/config``). Used only as a fallback when
    COB_CONFIG_DIR is unset: on a standard Ubuntu install this equals
    ``/usr/share/gnucobol/config`` (harmless, matches cobc's compiled-in
    default); on the msys2 build it repairs cobc's mis-encoded internal path.
    Returns None if the layout isn't recognised, leaving cobc's default."""
    candidate = cobc_dir.parent / "share" / "gnucobol" / "config"
    return str(candidate) if (candidate / "default.conf").is_file() else None


def _sandbox_env(cobc: str) -> dict[str, str]:
    """A minimal environment: cobc's directory + the OS baseline on PATH, the
    OS bootstrap vars, and any ``COB_*`` knobs the operator set (e.g.
    COB_CONFIG_DIR). The user's arbitrary PATH and other vars are not
    inherited."""
    env: dict[str, str] = {}
    for var in ("SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "LANG", "LC_ALL"):
        val = os.environ.get(var)
        if val:
            env[var] = val
    cobc_dir = Path(cobc).resolve().parent
    env["PATH"] = _baseline_path(str(cobc_dir))
    for key, val in os.environ.items():
        if key.startswith("COB_"):
            env[key] = val
    if "COB_CONFIG_DIR" not in env:
        config_dir = _derive_config_dir(cobc_dir)
        if config_dir is not None:
            env["COB_CONFIG_DIR"] = config_dir
    return env


def _normalize(text: str, tmpdir: Path) -> str:
    """Strip the (volatile) temp-dir path from diagnostics so messages are
    stable across calls."""
    return text.replace(str(tmpdir) + os.sep, "").replace(str(tmpdir), "")


def _parse_messages(cobc_output: str) -> list[str]:
    messages: list[str] = []
    for line in cobc_output.splitlines():
        line = line.strip()
        if _DIAG_RE.match(line):
            messages.append(line)
    return messages


# --------------------------------------------------------------------------
# D1: compile_check (syntax oracle)
# --------------------------------------------------------------------------

def compile_check(source: str) -> CompileResult:
    """Syntax-only compile of self-contained ``source`` (COPY statements must
    already be expanded — this signature takes no copybook path). Cheap and
    safe to call hundreds of times; never raises on COBOL errors."""
    cobc = _find_cobc()
    with tempfile.TemporaryDirectory(prefix="cobc_syn_") as tmp:
        tmpdir = Path(tmp)
        (tmpdir / _SRC_NAME).write_text(source, encoding="utf-8")
        proc = subprocess.run(
            [cobc, "-fsyntax-only", f"-std={_STD}", _SRC_NAME],
            cwd=tmp, env=_sandbox_env(cobc),
            capture_output=True, text=True, timeout=_RUN_TIMEOUT_S * 4,
        )
        output = _normalize((proc.stderr or "") + (proc.stdout or ""), tmpdir)
        return CompileResult(ok=proc.returncode == 0, messages=_parse_messages(output))


# --------------------------------------------------------------------------
# D2: run_cobol (compile + execute)
# --------------------------------------------------------------------------

def _cap(raw: bytes) -> str:
    if len(raw) > _OUTPUT_CAP:
        kept = raw[:_OUTPUT_CAP].decode("utf-8", errors="replace")
        return kept + f"\n...[truncated at {_OUTPUT_CAP} bytes]"
    return raw.decode("utf-8", errors="replace")


def _executable(tmpdir: Path) -> Path | None:
    for name in (_EXE_NAME, _EXE_NAME + ".exe"):
        candidate = tmpdir / name
        if candidate.is_file():
            return candidate
    return None


def _run_in_dir(source: str, inputs: RunInputs, tmpdir: Path) -> RunResult:
    cobc = _find_cobc()
    env = _sandbox_env(cobc)
    (tmpdir / _SRC_NAME).write_text(source, encoding="utf-8")
    for name, content in inputs.files.items():
        target = tmpdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    compile_proc = subprocess.run(
        [cobc, "-x", f"-std={_STD}", "-I", ".", "-o", _EXE_NAME, _SRC_NAME],
        cwd=str(tmpdir), env=env, capture_output=True, text=True, timeout=_RUN_TIMEOUT_S * 4,
    )
    exe = _executable(tmpdir)
    if compile_proc.returncode != 0 or exe is None:
        return RunResult(
            compiled_ok=False,
            stderr=_normalize((compile_proc.stderr or "") + (compile_proc.stdout or ""), tmpdir),
        )

    proc = subprocess.Popen(
        [str(exe)], cwd=str(tmpdir), env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    run_cobol.last_pid = proc.pid
    try:
        out, err = proc.communicate(input=inputs.stdin.encode("utf-8"), timeout=_RUN_TIMEOUT_S)
        return RunResult(
            compiled_ok=True, stdout=_cap(out), stderr=_cap(err),
            exit_code=proc.returncode, timed_out=False,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()  # reap — no zombie left behind
        return RunResult(
            compiled_ok=True, stdout=_cap(out), stderr=_cap(err),
            exit_code=None, timed_out=True,
        )


def run_cobol(source: str, inputs: RunInputs | None = None) -> RunResult:
    """Compile ``source`` with ``cobc -x`` and execute it in a fresh temp dir.

    Compile failure -> ``RunResult(compiled_ok=False, stderr=...)`` (never
    raises; expected for CICS programs). Execution is killed after
    ``_RUN_TIMEOUT_S`` (``timed_out=True``, ``exit_code=None``). A missing
    ``cobc`` binary raises RuntimeError."""
    result, _ = run_cobol_with_files(source, inputs)
    return result


def run_cobol_with_files(
    source: str, inputs: RunInputs | None = None,
) -> tuple[RunResult, dict[str, str]]:
    """Like :func:`run_cobol`, but also returns files the program left in its
    working directory (for T6.2 output capture). ``RunResult`` stays
    contract-exact; the extra dict rides alongside."""
    inputs = inputs or RunInputs()
    with tempfile.TemporaryDirectory(prefix="cobc_run_") as tmp:
        tmpdir = Path(tmp)
        seeded = {_SRC_NAME, _EXE_NAME, _EXE_NAME + ".exe", *inputs.files}
        result = _run_in_dir(source, inputs, tmpdir)
        outputs: dict[str, str] = {}
        if result.compiled_ok:
            for path in sorted(tmpdir.rglob("*")):
                if path.is_file() and path.name not in seeded:
                    rel = path.relative_to(tmpdir).as_posix()
                    outputs[rel] = path.read_text(encoding="utf-8", errors="replace")
        return result, outputs


run_cobol.last_pid = None  # child pid of the most recent execution (test introspection)
