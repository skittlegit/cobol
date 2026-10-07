"""Validate a migration patch with GnuCOBOL.

Checks, in order:

1. the patch applies to the original sources;
2. every changed line is inside the case's edit scope;
3. every host program compiles with its copybooks expanded;
4. every source assertion holds on the patched source;
5. the ``intended`` fixtures fail on the original source (so they really
   detect the drift) and every fixture passes on the patched source.

The patch passes only if every check passes. This is finite, fixture-level
evidence, not a proof of program equivalence.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cobol_archaeologist.migration import patch as patch_module
from cobol_archaeologist.migration.case import Fixture, MigrationCase
from cobol_archaeologist.model.run_cobol import compile_check, run_cobol
from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.tool_types import RunInputs

Status = Literal["pass", "fail"]
_PROCEDURE = re.compile(r"(?im)^.{7}PROCEDURE\s+DIVISION\s*\.\s*$")


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    status: Status
    detail: str


class Validation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    outcome: Status
    changed_lines: dict[str, list[int]]
    checks: list[Check]


def _host_file(files: dict[str, str], host: str) -> str:
    stem = Path(host).stem.upper()
    matches = [
        name
        for name in files
        if Path(name).suffix.lower() == ".cbl" and Path(name).stem.upper() == stem
    ]
    if len(matches) != 1:
        raise ValueError(f"host {host!r} does not name exactly one program")
    return matches[0]


class _Staged:
    """The case files written to a temporary directory for COPY resolution."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self._temp = tempfile.TemporaryDirectory(prefix="migration_")
        self.root = Path(self._temp.name)
        for name, text in files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def expanded(self, host: str) -> str:
        name = _host_file(self.files, host)
        paths = sorted({(self.root / n).parent for n in self.files}, key=str)
        return expand(self.files[name], paths).text

    def paragraphs(self, host: str) -> dict[str, str]:
        name = _host_file(self.files, host)
        program = parse_program(self.root / name, include_preamble=True)
        lines = self.files[name].splitlines()
        return {
            p.span.name: "\n".join(lines[p.span.line_start - 1 : p.span.line_end])
            for p in program.paragraphs
        }

    def close(self) -> None:
        self._temp.cleanup()


def _executable(text: str) -> str:
    return "\n".join(
        line[:72]
        for line in text.splitlines()
        if not (len(line) > 6 and line[6] in "*/")
    )


def run_fixture(staged: _Staged, fixture: Fixture) -> tuple[bool, str]:
    source = staged.expanded(fixture.host)
    if not fixture.run_original_main:
        known = set(staged.paragraphs(fixture.host))
        missing = set(fixture.perform) - known
        if missing:
            return False, f"absent paragraphs {sorted(missing)}"
        headers = list(_PROCEDURE.finditer(source))
        if len(headers) != 1:
            return False, "needs exactly one plain PROCEDURE DIVISION header"
        driver = (
            "\n"
            + "\n".join(
                "           " + statement
                for statement in (
                    *fixture.initialize,
                    *(f"PERFORM {name}" for name in fixture.perform),
                    *(f"DISPLAY {name}" for name in fixture.observe),
                    "STOP RUN.",
                )
            )
            + "\n"
        )
        position = headers[0].end()
        source = source[:position] + driver + source[position:]
    result = run_cobol(source, RunInputs(stdin=fixture.stdin))
    actual = result.stdout
    passed = (
        result.compiled_ok
        and result.exit_code == 0
        and not result.timed_out
        and actual == fixture.expected_stdout
    )
    detail = (
        f"{fixture.fixture_id}: expected {fixture.expected_stdout!r}, got {actual!r}"
        if result.compiled_ok
        else f"{fixture.fixture_id}: does not compile: {result.stderr[-300:]}"
    )
    return passed, detail


def _run_check(
    staged: _Staged, fixtures: tuple[Fixture, ...]
) -> tuple[bool, list[str]]:
    outcomes = [run_fixture(staged, fixture) for fixture in fixtures]
    return all(ok for ok, _ in outcomes), [d for ok, d in outcomes if not ok]


def validate(
    case: MigrationCase, sources: dict[str, str], patch_text: str
) -> Validation:
    checks: list[Check] = []

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append(
            Check(check_id=check_id, status="pass" if ok else "fail", detail=detail)
        )

    def done(changed: dict[str, set[int]]) -> Validation:
        return Validation(
            case_id=case.case_id,
            outcome="pass"
            if checks and all(c.status == "pass" for c in checks)
            else "fail",
            changed_lines={path: sorted(lines) for path, lines in changed.items()},
            checks=checks,
        )

    try:
        patched, changed = patch_module.apply(sources, patch_text)
    except patch_module.PatchError as exc:
        add("patch_apply", False, str(exc))
        return done({})
    add("patch_apply", True, f"changed {sum(map(len, changed.values()))} line(s)")
    outside = [
        f"{path}:{line}"
        for path, lines in changed.items()
        for line in sorted(lines)
        if not case.in_scope(path, line)
    ]
    add(
        "edit_scope",
        not outside,
        "outside scope: " + ", ".join(outside) if outside else "ok",
    )

    original, fixed = _Staged(sources), _Staged(patched)
    try:
        for host in case.hosts:
            result = compile_check(fixed.expanded(host))
            add(f"compile:{host}", result.ok, "; ".join(result.messages[:3]) or "ok")
        for assertion in case.assertions:
            text = (
                fixed.paragraphs(assertion.host).get(assertion.paragraph or "", "")
                if assertion.paragraph
                else fixed.expanded(assertion.host)
            )
            present = assertion.literal in _executable(text)
            add(
                f"assert:{assertion.assertion_id}",
                present == assertion.required,
                f"{assertion.literal!r} {'present' if present else 'absent'}",
            )
        before_ok, _ = _run_check(original, case.checks["intended"])
        add(
            "intended_detects_drift",
            not before_ok,
            "intended fixtures fail on the original source"
            if not before_ok
            else "intended fixtures already pass before the patch",
        )
        for check_id, fixtures in case.checks.items():
            ok, failures = _run_check(fixed, fixtures)
            add(
                f"behavior:{check_id}",
                ok,
                f"{len(fixtures)} fixture(s) pass" if ok else "; ".join(failures[:3]),
            )
    finally:
        original.close()
        fixed.close()
    return done(changed)
