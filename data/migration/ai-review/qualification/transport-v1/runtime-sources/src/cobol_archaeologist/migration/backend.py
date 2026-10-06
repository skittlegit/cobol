"""Pinned, provider-free parser/compiler and finite-fixture migration backend.

Execution fixtures insert a driver before the existing procedure paragraphs.
The original paragraphs and expanded COPY bodies remain unchanged. This is
paragraph-level behavior evidence, not a claim of complete program equivalence.
No fixture or unsupported static proof can silently become a passing check.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from tree_sitter import Parser

from cobol_archaeologist.ingest.cleaner import preprocess
from cobol_archaeologist.migration.contracts import (
    BehaviorCheck,
    FrozenSource,
    MigrationCase,
    ValidationCapability,
    normalized_relative_path,
)
from cobol_archaeologist.migration.validate import CheckObservation, CheckStatus
from cobol_archaeologist.model.cobc import find_cobc, inspect_cobc
from cobol_archaeologist.model.run_cobol import compile_check, run_cobol
from cobol_archaeologist.parser import _grammar
from cobol_archaeologist.parser._grammar import get_language
from cobol_archaeologist.parser.copybooks import expand
from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.static_analysis.call_graph import build_call_graph
from cobol_archaeologist.tool_types import RunInputs

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_PROCEDURE = re.compile(r"(?im)^.{7}PROCEDURE\s+DIVISION\s*\.\s*$")
_COPY = re.compile(r"(?im)^.{7}\s*COPY\b")
_EXEC = re.compile(r"(?im)^.{7}\s*EXEC\s+(?:CICS|SQL|DLI)\b")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ExecutionFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fixture_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    initialize: tuple[str, ...] = ()
    perform: tuple[str, ...] = ()
    observe: tuple[str, ...] = ()
    run_original_main: bool = False
    expected_stdout: str
    stdin: str = ""

    @model_validator(mode="after")
    def _bounded(self):
        if self.run_original_main:
            if self.initialize or self.perform or self.observe:
                raise ValueError("original-main fixtures cannot initialize, perform or inject observations")
        elif not self.perform or not self.observe:
            raise ValueError("paragraph-driver fixtures require perform and observe identifiers")
        for value in (*self.perform, *self.observe):
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError("fixture paragraphs/observations must be COBOL identifiers")
        for statement in self.initialize:
            # Initialization is trusted reviewed COBOL, limited to one fixed-
            # format line so it cannot rewrite divisions/target paragraphs.
            if "\n" in statement or "\r" in statement or len(statement) > 61:
                raise ValueError("initializers must fit one fixed-format statement line")
            if not re.match(r"^(MOVE|INITIALIZE|SET)\b", statement, re.IGNORECASE):
                raise ValueError("initializers may use MOVE, INITIALIZE or SET only")
            if re.search(r"(?<!\d)\.|\.(?!\d)", re.sub(r"(['\"]).*?\1", "", statement)):
                raise ValueError("initializer may not contain a sentence terminator")
        return self


class SourceAssertion(BaseModel):
    """Finite reviewed source consistency assertion; not a universal verifier."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    assertion_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    paragraph: str | None = None
    literal: str = Field(min_length=1)
    required: bool = True


class FixtureProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["migration-execution-fixtures-v1"] = "migration-execution-fixtures-v1"
    case_id: str
    frozen_sources: tuple[FrozenSource, ...] = Field(min_length=1)
    checks: dict[str, tuple[ExecutionFixture, ...]]
    source_assertions: tuple[SourceAssertion, ...] = ()
    fixture_authoring_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proof_scope: Literal["finite_case_execution_fixtures"] = "finite_case_execution_fixtures"

    @model_validator(mode="after")
    def _unique(self):
        source_names = [s.path.casefold() for s in self.frozen_sources]
        if len(set(source_names)) != len(source_names):
            raise ValueError("fixture source paths must be unique")
        for check_id, fixtures in self.checks.items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", check_id):
                raise ValueError("fixture check IDs must match BehaviorCheck identifiers")
            ids = [f.fixture_id for f in fixtures]
            if len(ids) != len(set(ids)):
                raise ValueError("fixture IDs must be unique within each check")
        assertion_ids = [a.assertion_id for a in self.source_assertions]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("source assertion IDs must be unique")
        return self

    @property
    def sha256(self) -> str:
        return _digest(self.model_dump(mode="json"))


class RealValidationBackend:
    """Implements ValidationBackend against a pinned case fixture protocol."""

    def __init__(self, fixtures: FixtureProtocol):
        self.fixtures = fixtures
        self._compiler_error: str | None = None
        try:
            binary = find_cobc()
            if binary is None:
                raise RuntimeError("GnuCOBOL is unavailable")
            info = inspect_cobc(binary)
            self.compiler = {"binary": str(Path(binary).resolve()),
                             "binary_sha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
                             "banner": info.banner, "version": info.version_text}
            native = Path(binary).resolve()
            if native.suffix.lower() in (".cmd", ".bat"):
                targets = re.findall(r'(?im)^"([^"\r\n]+cobc\.exe)"\s+%\*\s*$',
                                     native.read_text(encoding="utf-8-sig"))
                if len(targets) != 1:
                    raise RuntimeError("Compiler launcher does not name one explicit native cobc.exe")
                native = Path(targets[0]).resolve()
            self.compiler["native_binary"] = str(native)
            self.compiler["native_binary_sha256"] = hashlib.sha256(native.read_bytes()).hexdigest()
            self.compiler["cob_environment_sha256"] = _digest({k: v for k, v in os.environ.items()
                                                               if k.startswith("COB_")})
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.compiler = None
            self._compiler_error = str(exc)

    @property
    def identity_sha256(self) -> str:
        modules = [Path(__file__), Path(preprocess.__code__.co_filename),
                   Path(get_language.__code__.co_filename),
                   Path(inspect_cobc.__wrapped__.__code__.co_filename),
                   Path(expand.__code__.co_filename), Path(parse_program.__code__.co_filename),
                   Path(build_call_graph.__code__.co_filename), Path(compile_check.__code__.co_filename)]
        return _digest({"source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in modules},
                        "grammar": {"vendor_pin": (_grammar._VENDOR_DIR / "PINNED").read_text().strip(),
                            "shared_library_sha256": (hashlib.sha256(_grammar._LIB_PATH.read_bytes()).hexdigest()
                                if _grammar._LIB_PATH.exists() else "not_built")},
                        "fixture_protocol_sha256": self.fixtures.sha256,
                        "compiler": self.compiler})

    def capability_receipt(self) -> dict:
        """Identity/capability metadata, not evidence that any case passed."""
        return {"schema_version": "migration-real-backend-capability-v1",
                "backend_identity_sha256": self.identity_sha256,
                "fixture_protocol_sha256": self.fixtures.sha256,
                "compiler": self.compiler, "compiler_error": self._compiler_error,
                "supported": ["batch_executable", "copybook_fanout"],
                "cics_static": "unavailable_no_complete_static_proof_backend",
                "behavior_scope": self.fixtures.proof_scope,
                "case_checks_executed": False}

    def _obs(self, check_id, status, **details):
        return CheckObservation(check_id=check_id, status=status,
            log=json.dumps({"backend_identity_sha256": self.identity_sha256,
                            "fixture_protocol_sha256": self.fixtures.sha256, **details}, sort_keys=True))

    def _bind(self, case: MigrationCase, files: dict[str, str]) -> None:
        if case.case_id != self.fixtures.case_id or case.frozen_sources != self.fixtures.frozen_sources:
            raise ValueError("fixture protocol does not bind this frozen case/source roster")
        if set(files) != {s.path for s in case.frozen_sources}:
            raise ValueError("source paths differ from the frozen bundle")
        folded = set()
        for name in files:
            if normalized_relative_path(name) != name or name.casefold() in folded:
                raise ValueError("source path is unsafe or collides")
            folded.add(name.casefold())

    def _compiler_pin(self):
        binary = find_cobc()
        if self.compiler is None or binary is None:
            raise RuntimeError(self._compiler_error or "Pinned compiler is unavailable")
        if (str(Path(binary).resolve()) != self.compiler["binary"] or
                hashlib.sha256(Path(binary).read_bytes()).hexdigest() != self.compiler["binary_sha256"] or
                hashlib.sha256(Path(self.compiler["native_binary"]).read_bytes()).hexdigest() != self.compiler["native_binary_sha256"] or
                _digest({k: v for k, v in os.environ.items() if k.startswith("COB_")}) != self.compiler["cob_environment_sha256"]):
            raise RuntimeError("Compiler identity changed after backend construction")

    @contextmanager
    def _stage(self, case, files):
        self._bind(case, files)
        with tempfile.TemporaryDirectory(prefix="migration_backend_") as temp:
            root = Path(temp).resolve()
            for name, text in files.items():
                target = root / name
                if not target.resolve().is_relative_to(root):
                    raise ValueError("source path escapes case staging")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
            yield root

    def _path(self, root: Path, files, host: str) -> Path:
        matches = [root / name for name in files if Path(name).suffix.lower() == ".cbl"
                   and (name == host or Path(name).stem.upper() == Path(host).stem.upper())]
        if len(matches) != 1:
            raise ValueError(f"host does not identify exactly one frozen program: {host}")
        return matches[0]

    def _expanded(self, root, files, host):
        path = self._path(root, files, host)
        paths = sorted({(root / name).parent for name in files}, key=str)
        source = expand(path.read_text(encoding="utf-8"), paths).text
        if _COPY.search(source):
            raise ValueError("unresolved COPY remains in staged expansion")
        if _EXEC.search(source):
            raise ValueError("EXEC CICS/SQL/DLI execution is unsupported")
        return source

    def parse(self, case, files):
        try:
            with self._stage(case, files) as root:
                parser = Parser()
                parser.set_language(get_language())
                results = {}
                for name in files:
                    if Path(name).suffix.lower() != ".cbl":
                        continue
                    text = self._expanded(root, files, name)
                    tree = parser.parse(preprocess(text).text.encode())
                    results[name] = not tree.root_node.has_error
                if not results:
                    raise ValueError("no frozen COBOL program to parse")
                return self._obs("parser", CheckStatus.PASS if all(results.values()) else CheckStatus.FAIL,
                                 program_parser_results=results)
        except (OSError, RuntimeError, ValueError) as exc:
            return self._obs("parser", CheckStatus.UNAVAILABLE, error=str(exc))

    def compile(self, case, files, *, host=None):
        if case.validation_capability == ValidationCapability.CICS_STATIC:
            return self._obs("compile", CheckStatus.UNAVAILABLE,
                             error="CICS static cases have no executable validation capability")
        if self.compiler is None:
            return self._obs("compile", CheckStatus.UNAVAILABLE, error=self._compiler_error)
        try:
            self._compiler_pin()
            with self._stage(case, files) as root:
                result = compile_check(self._expanded(root, files, host or case.primary_program))
                return self._obs("compile", CheckStatus.PASS if result.ok else CheckStatus.FAIL,
                                 host=host or case.primary_program, compile_result=result.model_dump())
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return self._obs("compile", CheckStatus.UNAVAILABLE, error=str(exc))

    def static(self, case, files, *, host=None):
        if case.validation_capability == ValidationCapability.CICS_STATIC:
            return tuple(self._obs(check_id, CheckStatus.UNAVAILABLE,
                error="Complete CICS static proof is unsupported") for check_id in
                ("call_graph", "dataflow", "slice", "source_locus", "unresolved_references", "verifier_conflicts"))
        try:
            with self._stage(case, files) as root:
                programs = []
                preprocessed = {}
                for name in files:
                    if Path(name).suffix.lower() == ".cbl":
                        program = parse_program(root / name, include_preamble=True)
                        programs.append(program)
                        preprocessed[program.program_id] = preprocess(files[name])
                graph = build_call_graph(programs, preprocessed)
                compiled = self.compile(case, files, host=host)
                unresolved = [item.model_dump(mode="json") for item in graph.unresolved]
                refs_status = (CheckStatus.FAIL if unresolved else compiled.status)
                refs = self._obs("unresolved_references", refs_status,
                    unresolved_calls=unresolved, compiler_symbol_check=json.loads(compiled.log))
                selected = host or case.primary_program
                assertions = [a for a in self.fixtures.source_assertions if
                    host is None or Path(a.host).stem.upper() == Path(selected).stem.upper()]
                results = []
                for assertion in assertions:
                    text = self._expanded(root, files, assertion.host)
                    if assertion.paragraph:
                        program = next(p for p in programs if
                            Path(p.path).stem.upper() == Path(assertion.host).stem.upper())
                        paragraphs = [p for p in program.paragraphs if p.span.name == assertion.paragraph]
                        if len(paragraphs) != 1:
                            raise ValueError("source assertion names an absent/ambiguous paragraph")
                        p = paragraphs[0]
                        # Paragraph spans refer to original source, avoiding
                        # line offsets introduced by expanded data COPYs.
                        text = "\n".join(files[Path(program.path).relative_to(root).as_posix()].splitlines()[
                            p.span.line_start - 1:p.span.line_end])
                    # Comments are documentation, never evidence that a
                    # required executable source fact exists.
                    text = "\n".join(line[:72] for line in text.splitlines()
                                     if not (len(line) > 6 and line[6] in ("*", "/")))
                    results.append({"assertion_id": assertion.assertion_id,
                                    "passed": (assertion.literal in text) == assertion.required})
                status = CheckStatus.UNAVAILABLE if not results else (
                    CheckStatus.PASS if all(r["passed"] for r in results) else CheckStatus.FAIL)
                conflicts = self._obs("verifier_conflicts", status,
                    finite_source_assertions=results,
                    scope="Reviewed finite source consistency, not complete semantic equivalence")
                return refs, conflicts
        except (OSError, RuntimeError, ValueError) as exc:
            return tuple(self._obs(check_id, CheckStatus.UNAVAILABLE, error=str(exc))
                         for check_id in ("unresolved_references", "verifier_conflicts"))

    def behavior(self, case, files, check: BehaviorCheck):
        if case.validation_capability == ValidationCapability.CICS_STATIC:
            return self._obs(check.check_id, CheckStatus.UNAVAILABLE,
                             error="No complete CICS static behavior proof backend")
        fixtures = self.fixtures.checks.get(check.check_id, ())
        if not fixtures or self.compiler is None:
            return self._obs(check.check_id, CheckStatus.UNAVAILABLE,
                             error=self._compiler_error or "No pinned execution fixtures for this check")
        try:
            with self._stage(case, files) as root:
                normalized = lambda value: Path(value).stem.upper()
                if (case.validation_capability == ValidationCapability.COPYBOOK_FANOUT and
                        {normalized(f.host) for f in fixtures} != {normalized(h) for h in case.affected_hosts}):
                    raise ValueError("fixture check does not cover exactly the required host fan-out")
                results = []
                for fixture in fixtures:
                    self._compiler_pin()
                    original = self._expanded(root, files, fixture.host)
                    path = self._path(root, files, fixture.host)
                    program = parse_program(path, include_preamble=True)
                    known = {p.span.name for p in program.paragraphs}
                    if not set(fixture.perform) <= known:
                        raise ValueError("fixture performs an absent paragraph")
                    source = original
                    if not fixture.run_original_main:
                        headers = list(_PROCEDURE.finditer(original))
                        if len(headers) != 1:
                            raise ValueError("fixture requires one plain PROCEDURE DIVISION (no USING)")
                        driver = "\n" + "\n".join("           " + statement for statement in (
                            *fixture.initialize, *("PERFORM " + p for p in fixture.perform),
                            *("DISPLAY " + name for name in fixture.observe), "STOP RUN.")) + "\n"
                        position = headers[0].end()
                        source = original[:position] + driver + original[position:]
                    result = run_cobol(source, RunInputs(stdin=fixture.stdin))
                    actual = result.stdout.replace("\r\n", "\n")
                    expected = fixture.expected_stdout.replace("\r\n", "\n")
                    passed = result.compiled_ok and result.exit_code == 0 and not result.timed_out and actual == expected
                    results.append({"fixture_id": fixture.fixture_id, "host": fixture.host,
                        "passed": passed, "actual_stdout": actual, "expected_stdout": expected,
                        "instrumented_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                        "run_result": result.model_dump(mode="json")})
                return self._obs(check.check_id, CheckStatus.PASS if all(r["passed"] for r in results)
                                 else CheckStatus.FAIL, fixtures=results)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return self._obs(check.check_id, CheckStatus.UNAVAILABLE, error=str(exc))
