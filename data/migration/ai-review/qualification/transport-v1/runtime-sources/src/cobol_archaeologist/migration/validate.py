"""Offline T6.3 patch application, scope, and capability validation.

The validator consumes untrusted migration artifacts.  It never calls a model
and records every unavailable or failed check instead of dropping a case.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.migration.contracts import (
    BehaviorCheck,
    MigrationCase,
    MigrationRequest,
    MigrationTrack,
    PatchArtifact,
    ValidationCapability,
    normalized_relative_path,
)

_HUNK_RE = re.compile(
    r"^@@ -(?P<old>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new>\d+)(?:,(?P<new_count>\d+))? @@(?: .*)?$"
)


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class CaseOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ABSTENTION = "abstention"


class CheckObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str
    status: CheckStatus
    log: str


class MigrationValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_key: str
    case_id: str
    track: MigrationTrack
    capability: ValidationCapability
    outcome: CaseOutcome
    checks: tuple[CheckObservation, ...]
    changed_files: tuple[str, ...] = ()
    changed_line_count: int = Field(default=0, ge=0)
    affected_line_precision: float | None = Field(default=None, ge=0, le=1)
    unrelated_change_count: int = Field(default=0, ge=0)


class ValidationBackend(Protocol):
    """Pinned, case-local checks supplied by the T6 evaluation harness."""

    def parse(self, case: MigrationCase, files: dict[str, str]) -> CheckObservation: ...

    def static(
        self,
        case: MigrationCase,
        files: dict[str, str],
        *,
        host: str | None = None,
    ) -> tuple[CheckObservation, ...]: ...

    def compile(
        self,
        case: MigrationCase,
        files: dict[str, str],
        *,
        host: str | None = None,
    ) -> CheckObservation: ...

    def behavior(
        self,
        case: MigrationCase,
        files: dict[str, str],
        check: BehaviorCheck,
    ) -> CheckObservation: ...


@dataclass(frozen=True)
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    body: tuple[str, ...]


@dataclass(frozen=True)
class _FilePatch:
    path: str
    hunks: tuple[_Hunk, ...]


class PatchFormatError(ValueError):
    """Raised when a patch is unsafe or outside the supported unified format."""


def _diff_path(raw: str, prefix: str) -> str:
    value = raw[len(prefix) :].split("\t", 1)[0].strip()
    if value == "/dev/null":
        raise PatchFormatError("file creation/deletion is outside the frozen scope")
    if value.startswith(("a/", "b/")):
        value = value[2:]
    try:
        normalized = normalized_relative_path(value)
    except ValueError as exc:
        raise PatchFormatError(str(exc)) from exc
    if normalized != value:
        raise PatchFormatError("patch paths must use normalized POSIX spelling")
    return normalized


def parse_unified_patch(text: str) -> tuple[_FilePatch, ...]:
    """Parse modification-only unified diffs and reject ambiguous extensions."""

    lines = text.splitlines()
    patches: list[_FilePatch] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith(("diff --git ", "index ")):
            index += 1
            continue
        if line.startswith(
            ("new file mode ", "deleted file mode ", "rename ", "Binary ")
        ):
            raise PatchFormatError("patch may modify existing text files only")
        if not line.startswith("--- "):
            raise PatchFormatError(f"unexpected patch line: {line!r}")
        old_path = _diff_path(line, "--- ")
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise PatchFormatError("missing +++ file header")
        new_path = _diff_path(lines[index], "+++ ")
        if old_path != new_path:
            raise PatchFormatError("renames are outside the frozen scope")
        index += 1
        hunks: list[_Hunk] = []
        while index < len(lines) and lines[index].startswith("@@ "):
            match = _HUNK_RE.fullmatch(lines[index])
            if match is None:
                raise PatchFormatError(f"invalid hunk header: {lines[index]!r}")
            old_count = int(match.group("old_count") or "1")
            new_count = int(match.group("new_count") or "1")
            hunk_header = lines[index]
            index += 1
            body: list[str] = []
            while index < len(lines):
                candidate = lines[index]
                if candidate.startswith(("@@ ", "--- ", "diff --git ")):
                    break
                if candidate == r"\ No newline at end of file":
                    index += 1
                    continue
                if not candidate.startswith((" ", "+", "-")):
                    raise PatchFormatError(f"invalid hunk body line: {candidate!r}")
                body.append(candidate)
                index += 1
            observed_old = sum(line[0] in {" ", "-"} for line in body)
            observed_new = sum(line[0] in {" ", "+"} for line in body)
            if observed_old != old_count or observed_new != new_count:
                raise PatchFormatError(
                    f"hunk counts do not match {hunk_header!r}: "
                    f"old {observed_old}/{old_count}, new {observed_new}/{new_count}"
                )
            hunks.append(
                _Hunk(
                    old_start=int(match.group("old")),
                    old_count=old_count,
                    new_start=int(match.group("new")),
                    new_count=new_count,
                    body=tuple(body),
                )
            )
        if not hunks:
            raise PatchFormatError(f"file patch for {old_path!r} has no hunks")
        patches.append(_FilePatch(path=old_path, hunks=tuple(hunks)))
    if not patches:
        raise PatchFormatError("patch contains no file modifications")
    paths = [patch.path for patch in patches]
    if len(paths) != len(set(paths)):
        raise PatchFormatError("each file must appear in exactly one patch section")
    return tuple(patches)


def _apply_file_patch(source: str, patch: _FilePatch) -> tuple[str, set[int]]:
    original = source.splitlines()
    trailing_newline = source.endswith(("\n", "\r"))
    output: list[str] = []
    cursor = 0
    changed_anchors: set[int] = set()
    for hunk in patch.hunks:
        start = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if start < cursor or start > len(original):
            raise PatchFormatError(f"overlapping or out-of-range hunk in {patch.path}")
        output.extend(original[cursor:start])
        cursor = start
        old_line = hunk.old_start
        last_removed: int | None = None
        for row in hunk.body:
            marker, content = row[0], row[1:]
            if marker in {" ", "-"}:
                if cursor >= len(original) or original[cursor] != content:
                    raise PatchFormatError(
                        f"patch context does not match {patch.path}:{old_line}"
                    )
                if marker == " ":
                    output.append(content)
                    last_removed = None
                else:
                    changed_anchors.add(old_line)
                    last_removed = old_line
                cursor += 1
                old_line += 1
            else:
                output.append(content)
                # Insertions are scoped to the adjacent frozen-source line.
                anchor = last_removed or min(max(old_line, 1), max(len(original), 1))
                changed_anchors.add(anchor)
    output.extend(original[cursor:])
    rendered = "\n".join(output)
    if trailing_newline:
        rendered += "\n"
    return rendered, changed_anchors


def _inside_scope(case: MigrationCase, path: str, line: int) -> bool:
    return any(
        scope.path == path
        and any(start <= line <= end for start, end in scope.line_spans)
        for scope in case.allowed_source_scope
    )


def _reported_precision(
    artifact: PatchArtifact,
    actual: dict[str, set[int]],
) -> tuple[float, int]:
    reported: set[tuple[str, int]] = set()
    for location in artifact.affected_locations:
        start, end = location.line_span
        reported.update((location.path, line) for line in range(start, end + 1))
    actual_flat = {
        (path, line) for path, changed_lines in actual.items() for line in changed_lines
    }
    if not reported:
        return 0.0, len(actual_flat)
    precision = len(actual_flat & reported) / len(reported)
    unrelated = len(actual_flat - reported)
    return precision, unrelated


def _failure(check_id: str, log: str) -> CheckObservation:
    return CheckObservation(check_id=check_id, status=CheckStatus.FAIL, log=log)


def _require_backend_check_id(
    observation: CheckObservation,
    expected: str,
    *,
    context: str,
) -> CheckObservation:
    if observation.check_id != expected:
        return _failure(
            expected,
            f"{context} returned unexpected check ID {observation.check_id!r}; "
            f"expected {expected!r}",
        )
    return observation


def _require_checks(
    checks: tuple[CheckObservation, ...],
    required: set[str],
    *,
    context: str,
) -> list[CheckObservation]:
    observed = {check.check_id for check in checks}
    return [
        _failure(check_id, f"required {context} check was not supplied")
        for check_id in sorted(required - observed)
    ]


def _hash_gate(case: MigrationCase, files: dict[str, str]) -> CheckObservation:
    problems: list[str] = []
    expected_paths = {source.path for source in case.frozen_sources}
    if set(files) != expected_paths:
        problems.append(
            f"source set mismatch: expected {sorted(expected_paths)}, got {sorted(files)}"
        )
    for source in case.frozen_sources:
        if source.path not in files:
            continue
        observed = hashlib.sha256(files[source.path].encode()).hexdigest()
        if observed != source.sha256:
            problems.append(
                f"{source.path}: expected {source.sha256}, observed {observed}"
            )
    if problems:
        return _failure("frozen_source_hash", "; ".join(problems))
    return CheckObservation(
        check_id="frozen_source_hash",
        status=CheckStatus.PASS,
        log="all staged sources match the frozen hashes",
    )


def validate_migration(
    request: MigrationRequest,
    artifact: PatchArtifact,
    *,
    expected_track: MigrationTrack,
    base_files: dict[str, str],
    backend: ValidationBackend,
) -> MigrationValidation:
    """Validate one artifact and retain a complete, non-silent check record."""

    from cobol_archaeologist.migration.agent import validate_artifact_identity

    validate_artifact_identity(request, artifact)
    if request.track != expected_track:
        raise ValueError("migration request track differs from the expected track")
    case = request.case
    if not case.eligible_for_evaluation:
        raise ValueError("migration case is not reviewed/evaluation-eligible")
    if artifact.abstained:
        return MigrationValidation(
            run_key=artifact.run_key,
            case_id=case.case_id,
            track=artifact.track,
            capability=case.validation_capability,
            outcome=CaseOutcome.ABSTENTION,
            checks=(
                CheckObservation(
                    check_id="abstention",
                    status=CheckStatus.NOT_APPLICABLE,
                    log=artifact.abstention_reason or "explicit abstention",
                ),
            ),
        )

    checks: list[CheckObservation] = []
    hash_check = _hash_gate(case, base_files)
    checks.append(hash_check)
    if hash_check.status != CheckStatus.PASS:
        return _failed_result(case, artifact, checks)

    try:
        parsed = parse_unified_patch(artifact.patch or "")
        patched = dict(base_files)
        actual: dict[str, set[int]] = {}
        for file_patch in parsed:
            if file_patch.path not in base_files:
                raise PatchFormatError(f"patch names unfrozen file {file_patch.path!r}")
            rendered, changed = _apply_file_patch(
                base_files[file_patch.path], file_patch
            )
            if rendered == base_files[file_patch.path]:
                raise PatchFormatError(
                    f"patch section for {file_patch.path!r} makes no source change"
                )
            patched[file_patch.path] = rendered
            actual[file_patch.path] = changed
        if not any(actual.values()):
            raise PatchFormatError("patch makes no source changes")
        checks.append(
            CheckObservation(
                check_id="patch_apply",
                status=CheckStatus.PASS,
                log="patch applies exactly to the hash-verified staged source",
            )
        )
    except PatchFormatError as exc:
        checks.append(_failure("patch_apply", str(exc)))
        return _failed_result(case, artifact, checks)

    out_of_scope = sorted(
        f"{path}:{line}"
        for path, lines in actual.items()
        for line in lines
        if not _inside_scope(case, path, line)
    )
    scope_check = (
        _failure("allowed_source_scope", f"out-of-scope changes: {out_of_scope}")
        if out_of_scope
        else CheckObservation(
            check_id="allowed_source_scope",
            status=CheckStatus.PASS,
            log="all changed lines are within the frozen allowlist",
        )
    )
    checks.append(scope_check)
    precision, unrelated = _reported_precision(artifact, actual)
    reported_out_of_scope = sorted(
        f"{location.path}:{line}"
        for location in artifact.affected_locations
        for line in range(location.line_span[0], location.line_span[1] + 1)
        if not _inside_scope(case, location.path, line)
    )
    if unrelated or reported_out_of_scope:
        details: list[str] = []
        if unrelated:
            details.append(f"{unrelated} changed source line(s) were not disclosed")
        if reported_out_of_scope:
            details.append(
                f"reported affected locations exceed the allowlist: "
                f"{reported_out_of_scope}"
            )
        checks.append(
            _failure(
                "affected_locations",
                "; ".join(details),
            )
        )
    else:
        checks.append(
            CheckObservation(
                check_id="affected_locations",
                status=CheckStatus.PASS,
                log=f"affected-line precision={precision:.6f}",
            )
        )
    if scope_check.status != CheckStatus.PASS or unrelated or reported_out_of_scope:
        return _failed_result(
            case,
            artifact,
            checks,
            actual=actual,
            precision=precision,
            unrelated=len(out_of_scope),
        )

    try:
        parsed_source = backend.parse(case, patched)
    except (OSError, RuntimeError, ValueError) as exc:
        parsed_source = _failure("parser", f"validation backend raised: {exc}")
    if parsed_source.check_id != "parser":
        parsed_source = _failure(
            "parser", f"backend returned unexpected check ID {parsed_source.check_id!r}"
        )
    checks.append(parsed_source)
    capability = case.validation_capability
    if capability == ValidationCapability.BATCH_EXECUTABLE:
        try:
            static = backend.static(case, patched)
        except (OSError, RuntimeError, ValueError) as exc:
            static = (_failure("static", f"validation backend raised: {exc}"),)
        checks.extend(static)
        checks.extend(
            _require_checks(
                static,
                {"unresolved_references", "verifier_conflicts"},
                context="batch safety",
            )
        )
        try:
            compiled = backend.compile(case, patched)
        except (OSError, RuntimeError, ValueError) as exc:
            compiled = _failure("compile", f"validation backend raised: {exc}")
        checks.append(
            _require_backend_check_id(compiled, "compile", context="compile backend")
        )
    elif capability == ValidationCapability.CICS_STATIC:
        checks.append(
            CheckObservation(
                check_id="compile",
                status=CheckStatus.UNAVAILABLE,
                log="CICS case is not executable under the pinned GnuCOBOL harness",
            )
        )
        try:
            static = backend.static(case, patched)
        except (OSError, RuntimeError, ValueError) as exc:
            static = (_failure("static", f"validation backend raised: {exc}"),)
        checks.extend(static)
        required = {
            "call_graph",
            "dataflow",
            "slice",
            "source_locus",
            "unresolved_references",
            "verifier_conflicts",
        }
        checks.extend(_require_checks(static, required, context="CICS static"))
    else:
        for host in case.affected_hosts:
            try:
                static = backend.static(case, patched, host=host)
            except (OSError, RuntimeError, ValueError) as exc:
                static = (_failure("static", f"validation backend raised: {exc}"),)
            checks.extend(
                check.model_copy(update={"check_id": f"host:{host}:{check.check_id}"})
                for check in static
            )
            checks.extend(
                check.model_copy(update={"check_id": f"host:{host}:{check.check_id}"})
                for check in _require_checks(
                    static,
                    {"unresolved_references", "verifier_conflicts"},
                    context=f"copybook host {host} safety",
                )
            )
            try:
                compiled = backend.compile(case, patched, host=host)
            except (OSError, RuntimeError, ValueError) as exc:
                compiled = _failure("compile", f"validation backend raised: {exc}")
            compiled = _require_backend_check_id(
                compiled, "compile", context=f"compile backend for host {host}"
            )
            checks.append(
                compiled.model_copy(update={"check_id": f"host:{host}:compile"})
            )

    try:
        intended = backend.behavior(case, patched, case.intended_behavior)
    except (OSError, RuntimeError, ValueError) as exc:
        intended = _failure("intended_behavior", f"validation backend raised: {exc}")
    intended = _require_backend_check_id(
        intended,
        case.intended_behavior.check_id,
        context="intended-behavior backend",
    )
    checks.append(intended.model_copy(update={"check_id": "intended_behavior"}))
    for regression in case.unaffected_regressions:
        try:
            observed = backend.behavior(case, patched, regression)
        except (OSError, RuntimeError, ValueError) as exc:
            observed = _failure(
                regression.check_id, f"validation backend raised: {exc}"
            )
        observed = _require_backend_check_id(
            observed,
            regression.check_id,
            context="regression backend",
        )
        checks.append(
            observed.model_copy(
                update={"check_id": f"regression:{regression.check_id}"}
            )
        )

    expected_unavailable = {
        "compile"
        if capability == ValidationCapability.CICS_STATIC
        else "__no_unavailable_check__"
    }
    outcome = CaseOutcome.PASS
    for check in checks:
        if check.status == CheckStatus.PASS:
            continue
        if (
            check.status == CheckStatus.UNAVAILABLE
            and check.check_id in expected_unavailable
        ):
            continue
        outcome = CaseOutcome.FAIL
        break
    return MigrationValidation(
        run_key=artifact.run_key,
        case_id=case.case_id,
        track=artifact.track,
        capability=capability,
        outcome=outcome,
        checks=tuple(checks),
        changed_files=tuple(sorted(actual)),
        changed_line_count=sum(len(lines) for lines in actual.values()),
        affected_line_precision=precision,
        unrelated_change_count=len(out_of_scope),
    )


def _failed_result(
    case: MigrationCase,
    artifact: PatchArtifact,
    checks: list[CheckObservation],
    *,
    actual: dict[str, set[int]] | None = None,
    precision: float | None = None,
    unrelated: int = 0,
) -> MigrationValidation:
    actual = actual or {}
    return MigrationValidation(
        run_key=artifact.run_key,
        case_id=case.case_id,
        track=artifact.track,
        capability=case.validation_capability,
        outcome=CaseOutcome.FAIL,
        checks=tuple(checks),
        changed_files=tuple(sorted(actual)),
        changed_line_count=sum(len(lines) for lines in actual.values()),
        affected_line_precision=precision,
        unrelated_change_count=unrelated,
    )
