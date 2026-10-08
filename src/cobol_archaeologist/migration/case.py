"""A migration case: a verified finding, its source, and how a fix is checked.

Each case lives in ``data/migration/<case_id>/``:

- ``case.json``       this model
- ``sources/``        the original program and copybook files
- ``patch.diff``      the generated unified diff (once generated)
- ``patch.json``      the patch rationale and intended behaviour
- ``validation.json`` the result of validating the patch
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.schemas import DriftPrediction

ROOT = Path(__file__).resolve().parents[3]
MIGRATION_ROOT = ROOT / "data" / "migration"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class Fixture(BaseModel):
    """One finite behaviour check run under GnuCOBOL.

    A paragraph-driver fixture inserts ``initialize`` statements, ``PERFORM``s
    of the named paragraphs, and ``DISPLAY``s of the observed fields at the top
    of the procedure division. ``run_original_main`` runs the program as is.
    """

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
    def _bounded(self) -> Fixture:
        if self.run_original_main:
            if self.initialize or self.perform or self.observe:
                raise ValueError("an original-main fixture cannot inject statements")
        elif not self.perform or not self.observe:
            raise ValueError("a driver fixture needs perform and observe")
        for name in (*self.perform, *self.observe):
            if not _IDENTIFIER.fullmatch(name):
                raise ValueError(f"not a COBOL identifier: {name!r}")
        for statement in self.initialize:
            if "\n" in statement or len(statement) > 61:
                raise ValueError("an initializer must fit one fixed-format line")
            if not re.match(r"^(MOVE|INITIALIZE|SET)\b", statement, re.IGNORECASE):
                raise ValueError("initializers may use MOVE, INITIALIZE, or SET only")
            if re.search(r"(?<!\d)\.|\.(?!\d)", re.sub(r"(['\"]).*?\1", "", statement)):
                raise ValueError("an initializer may not end a sentence")
        return self


class SourceAssertion(BaseModel):
    """A literal that must (or must not) appear in a host's executable source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assertion_id: str = Field(min_length=1)
    host: str = Field(min_length=1)
    paragraph: str | None = None
    literal: str = Field(min_length=1)
    required: bool = True


class EditScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    line_spans: tuple[tuple[int, int], ...] = Field(min_length=1)


class MigrationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^migration_[a-z0-9_-]+$")
    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    # "oracle": the finding is the benchmark gold (an upper bound on migration);
    # "detector": a verified detector finding.
    finding_source: Literal["oracle", "detector"]
    finding: DriftPrediction
    primary_program: str
    hosts: tuple[str, ...] = Field(min_length=1)
    edit_scope: tuple[EditScope, ...] = Field(min_length=1)
    intended_behavior: str = Field(min_length=1)
    checks: dict[str, tuple[Fixture, ...]]
    assertions: tuple[SourceAssertion, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> MigrationCase:
        if self.finding.instance_id != self.instance_id:
            raise ValueError("finding belongs to a different instance")
        if "intended" not in self.checks:
            raise ValueError("a case needs an 'intended' behaviour check")
        if not any(check != "intended" for check in self.checks):
            raise ValueError("a case needs at least one regression check")
        return self

    def in_scope(self, path: str, line: int) -> bool:
        return any(
            scope.path == path and any(a <= line <= b for a, b in scope.line_spans)
            for scope in self.edit_scope
        )


def case_dir(case_id: str, root: Path = MIGRATION_ROOT) -> Path:
    return root / case_id


def load_case(
    case_id: str, root: Path = MIGRATION_ROOT
) -> tuple[MigrationCase, dict[str, str]]:
    directory = case_dir(case_id, root)
    case = MigrationCase.model_validate_json(
        (directory / "case.json").read_text(encoding="utf-8")
    )
    sources = {
        path.relative_to(directory / "sources").as_posix(): path.read_text(
            encoding="utf-8"
        )
        for path in sorted((directory / "sources").rglob("*"))
        if path.is_file()
    }
    for name in sources:
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
            raise ValueError(f"unsafe source path {name!r}")
    return case, sources


def case_ids(root: Path = MIGRATION_ROOT) -> list[str]:
    return sorted(
        path.name for path in root.iterdir() if (path / "case.json").is_file()
    )
