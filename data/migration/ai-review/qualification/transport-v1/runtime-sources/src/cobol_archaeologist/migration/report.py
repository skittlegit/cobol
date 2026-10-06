"""T6.4 reporting with non-pooled detector and oracle tracks."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.migration.contracts import (
    MigrationCase,
    MigrationRequest,
    MigrationTrack,
    MigrationValidationProtocol,
    PatchArtifact,
    ValidationArtifactPin,
    ValidationCapability,
)
from cobol_archaeologist.migration.roster import load_canonical_roster
from cobol_archaeologist.migration.validate import (
    CaseOutcome,
    CheckObservation,
    CheckStatus,
    MigrationValidation,
    ValidationBackend,
    validate_migration,
)

if TYPE_CHECKING:
    from cobol_archaeologist.eval.config3_live import Config3RunFreeze


class Rate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: int = Field(ge=0)
    denominator: int = Field(ge=0)
    unavailable: int = Field(default=0, ge=0)
    value: float | None = Field(ge=0, le=1)


class TrackReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    eligible: int
    eligibility_status: Literal["eligible", "ineligible_config3_decision"]
    eligibility_reason: str | None = None
    evaluated: int
    patch_rate: Rate
    abstention_rate: Rate
    apply_rate: Rate
    parse_rate: Rate
    compile_rate: Rate
    intended_test_rate: Rate
    regression_rate: Rate
    pass_rate: Rate
    by_drift_type: dict[str, dict[str, int]]
    by_stratum: dict[str, dict[str, int]]
    by_capability: dict[str, dict[str, int]]
    affected_line_precision_mean: float | None
    unrelated_change_count: int
    total_turns: int
    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: int
    total_interruptions: int
    resumed_runs: int
    successful_case_ids: tuple[str, ...]
    failed_case_ids: tuple[str, ...]
    abstained_case_ids: tuple[str, ...]


class MigrationReport(BaseModel):
    """No combined performance field exists: tracks cannot be pooled."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roster_sha256: str
    roster_case_ids: tuple[str, ...]
    tracks: dict[MigrationTrack, TrackReport]
    config3_decision_sha256: str
    config3_decision_status: Literal["GO", "NO_GO", "NOT_EVALUABLE"]
    detector_utility_gate_passed: bool
    detector_led_valid_patch_evidence: bool
    end_to_end_migration_claim_supported: bool
    oracle_assisted_is_upper_bound_only: bool = True
    release_relationship: str


def _canonical_model_hash(model: BaseModel) -> str:
    raw = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def validation_backend_sha256(backend: ValidationBackend) -> str:
    """Hash the concrete backend implementation and its qualified identity."""

    backend_type = type(backend)
    source_path = inspect.getsourcefile(backend_type)
    if source_path is None:
        raise ValueError("validation backend must have a hashable source file")
    material = {
        "module": backend_type.__module__,
        "qualname": backend_type.__qualname__,
        "source_sha256": hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def migration_validator_sha256() -> str:
    """Return the exact offline validator implementation hash."""

    from cobol_archaeologist.migration import validate as validate_module

    return hashlib.sha256(Path(validate_module.__file__).read_bytes()).hexdigest()


def _load_registered_validation_backend(
    *,
    protocol_root: Path,
    cases: list[MigrationCase],
) -> tuple[MigrationValidationProtocol, ValidationBackend]:
    root = Path(protocol_root).resolve()
    path = (root / "validation-protocol.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("validation protocol escapes its canonical root") from exc
    raw = path.read_bytes()
    observed_protocol_sha256 = hashlib.sha256(raw).hexdigest()
    if any(
        case.validation_protocol_sha256 != observed_protocol_sha256 for case in cases
    ):
        raise ValueError("canonical roster does not pin the validation protocol")
    protocol = MigrationValidationProtocol.model_validate_json(raw)
    if protocol.validator_sha256 != migration_validator_sha256():
        raise ValueError("validation protocol pins a different validator implementation")
    module = importlib.import_module(protocol.backend_module)
    backend_type = module
    for component in protocol.backend_qualname.split("."):
        backend_type = getattr(backend_type, component, None)
        if backend_type is None:
            raise ValueError("validation protocol backend is absent from its module")
    if not inspect.isclass(backend_type):
        raise ValueError("validation protocol backend registry target is not a class")
    backend = backend_type()
    if validation_backend_sha256(backend) != protocol.backend_sha256:
        raise ValueError("registered validation backend implementation hash mismatch")
    return protocol, backend


def _required_pass_checks(case: MigrationCase) -> dict[str, CheckStatus]:
    expected = {
        "frozen_source_hash": CheckStatus.PASS,
        "patch_apply": CheckStatus.PASS,
        "allowed_source_scope": CheckStatus.PASS,
        "affected_locations": CheckStatus.PASS,
        "parser": CheckStatus.PASS,
        "intended_behavior": CheckStatus.PASS,
        **{
            f"regression:{check.check_id}": CheckStatus.PASS
            for check in case.unaffected_regressions
        },
    }
    if case.validation_capability == ValidationCapability.CICS_STATIC:
        expected.update(
            {
                "compile": CheckStatus.UNAVAILABLE,
                "call_graph": CheckStatus.PASS,
                "dataflow": CheckStatus.PASS,
                "slice": CheckStatus.PASS,
                "source_locus": CheckStatus.PASS,
                "unresolved_references": CheckStatus.PASS,
                "verifier_conflicts": CheckStatus.PASS,
            }
        )
    elif case.validation_capability == ValidationCapability.BATCH_EXECUTABLE:
        expected.update(
            {
                "compile": CheckStatus.PASS,
                "unresolved_references": CheckStatus.PASS,
                "verifier_conflicts": CheckStatus.PASS,
            }
        )
    else:
        for host in case.affected_hosts:
            expected.update(
                {
                    f"host:{host}:compile": CheckStatus.PASS,
                    f"host:{host}:unresolved_references": CheckStatus.PASS,
                    f"host:{host}:verifier_conflicts": CheckStatus.PASS,
                }
            )
    return expected


def _validate_check_roster(
    validation: MigrationValidation,
    case: MigrationCase,
) -> None:
    check_by_id = {check.check_id: check for check in validation.checks}
    if len(check_by_id) != len(validation.checks):
        raise ValueError("validation check IDs must be unique")
    if validation.outcome == CaseOutcome.ABSTENTION:
        if set(check_by_id) != {"abstention"} or (
            check_by_id["abstention"].status != CheckStatus.NOT_APPLICABLE
        ):
            raise ValueError("abstention validation has an invalid check roster")
        return
    if validation.outcome == CaseOutcome.PASS:
        expected = _required_pass_checks(case)
        missing = set(expected) - set(check_by_id)
        if missing:
            raise ValueError(
                f"PASS validation is missing required checks: {sorted(missing)}"
            )
        wrong = {
            check_id: check_by_id[check_id].status
            for check_id, status in expected.items()
            if check_by_id[check_id].status != status
        }
        disallowed = {
            check.check_id: check.status
            for check in validation.checks
            if check.status != CheckStatus.PASS
            and not (
                case.validation_capability == ValidationCapability.CICS_STATIC
                and check.check_id == "compile"
                and check.status == CheckStatus.UNAVAILABLE
            )
        }
        if wrong or disallowed:
            raise ValueError(
                "PASS validation contains failed, unavailable, or incorrectly "
                f"statused checks: {wrong | disallowed}"
            )
        return
    permitted_unavailable = (
        {"compile"}
        if case.validation_capability == ValidationCapability.CICS_STATIC
        else set()
    )
    if not any(
        check.status == CheckStatus.FAIL
        or (
            check.status in {CheckStatus.UNAVAILABLE, CheckStatus.NOT_APPLICABLE}
            and check.check_id not in permitted_unavailable
        )
        for check in validation.checks
    ):
        raise ValueError("FAIL validation contains no failing check evidence")


def _load_validation_artifacts(
    pins: list[ValidationArtifactPin],
    *,
    root: Path,
    request_by_case_track: dict[tuple[str, MigrationTrack], MigrationRequest],
    artifact_by_key: dict[tuple[str, MigrationTrack], PatchArtifact],
    canonical_source_root: Path,
    backend: ValidationBackend,
    validation_protocol: MigrationValidationProtocol,
) -> list[MigrationValidation]:
    root = Path(root).resolve()
    canonical_source_root = Path(canonical_source_root).resolve()
    observed_backend_sha256 = validation_backend_sha256(backend)
    observed_validator_sha256 = migration_validator_sha256()
    validations: list[MigrationValidation] = []
    pin_keys: set[tuple[str, MigrationTrack]] = set()
    for pin in pins:
        key = (pin.run_key, pin.track)
        if key in pin_keys:
            raise ValueError("validation pins must be unique by run key and track")
        pin_keys.add(key)
        artifact = artifact_by_key.get(key)
        request = request_by_case_track.get((pin.case_id, pin.track))
        if artifact is None or request is None:
            raise ValueError("validation pin has no matching request and artifact")
        if pin.case_id != artifact.case_id:
            raise ValueError("validation pin case ID differs from its artifact")
        if pin.request_sha256 != _canonical_model_hash(request):
            raise ValueError("validation pin request hash mismatch")
        if pin.artifact_sha256 != _canonical_model_hash(artifact):
            raise ValueError("validation pin patch-artifact hash mismatch")
        if (
            pin.validator_sha256 != observed_validator_sha256
            or pin.validator_sha256 != validation_protocol.validator_sha256
        ):
            raise ValueError("validation pin validator implementation hash mismatch")
        if (
            pin.backend_sha256 != observed_backend_sha256
            or pin.backend_sha256 != validation_protocol.backend_sha256
        ):
            raise ValueError("validation pin backend implementation hash mismatch")
        if (
            pin.runtime_source_sha256 != request.method.runtime_source_sha256
            or pin.runtime_source_sha256 != validation_protocol.runtime_source_sha256
        ):
            raise ValueError("validation pin runtime source hash mismatch")
        path = (root / pin.path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("validation artifact escapes its evidence root") from exc
        raw = path.read_bytes()
        observed = hashlib.sha256(raw).hexdigest()
        if observed != pin.sha256:
            raise ValueError("validation artifact content hash mismatch")
        validation = MigrationValidation.model_validate_json(raw)
        if (
            validation.run_key != pin.run_key
            or validation.case_id != pin.case_id
            or validation.track != pin.track
            or validation.capability != request.case.validation_capability
        ):
            raise ValueError("validation artifact identity differs from its pin")
        _validate_check_roster(validation, request.case)
        base_files: dict[str, str] = {}
        for frozen_source in request.case.frozen_sources:
            source_path = (canonical_source_root / frozen_source.path).resolve()
            try:
                source_path.relative_to(canonical_source_root)
            except ValueError as exc:
                raise ValueError("canonical validation source escapes its root") from exc
            base_files[frozen_source.path] = source_path.read_bytes().decode("utf-8")
        replayed = validate_migration(
            request,
            artifact,
            expected_track=request.track,
            base_files=base_files,
            backend=backend,
        )
        if replayed != validation:
            raise ValueError(
                "pinned validation differs from deterministic validator replay"
            )
        validations.append(validation)
    if pin_keys != set(artifact_by_key):
        raise ValueError("every patch artifact requires exactly one pinned validation")
    return validations


def _rate(passed: int, denominator: int, unavailable: int = 0) -> Rate:
    return Rate(
        passed=passed,
        denominator=denominator,
        unavailable=unavailable,
        value=(passed / denominator if denominator else None),
    )


def _check_rate(
    validations: list[MigrationValidation],
    predicate,
) -> Rate:
    checks: list[CheckObservation] = [
        check
        for validation in validations
        for check in validation.checks
        if predicate(check.check_id)
    ]
    unavailable = sum(check.status == CheckStatus.UNAVAILABLE for check in checks)
    scored = [
        check
        for check in checks
        if check.status not in {CheckStatus.UNAVAILABLE, CheckStatus.NOT_APPLICABLE}
    ]
    return _rate(
        sum(check.status == CheckStatus.PASS for check in scored),
        len(scored),
        unavailable,
    )


def _breakdown(
    validations: list[MigrationValidation],
    case_by_id: dict[str, MigrationCase],
    attribute: str,
) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for validation in validations:
        case = case_by_id[validation.case_id]
        key = str(getattr(case, attribute))
        grouped[key][validation.outcome.value] += 1
    return {
        key: dict(sorted(counts.items())) for key, counts in sorted(grouped.items())
    }


def build_migration_report(
    requests: list[MigrationRequest],
    artifacts: list[PatchArtifact],
    validation_pins: list[ValidationArtifactPin],
    *,
    validation_evidence_root: Path,
    canonical_source_root: Path,
    canonical_roster_path: Path,
    review_evidence_root: Path,
    protocol_root: Path,
    config3_output_dir: Path,
    config3_freeze: Config3RunFreeze,
) -> MigrationReport:
    """Reconcile frozen roster, raw artifacts, and validations by track."""

    from cobol_archaeologist.eval.config3_live import (
        load_revalidate_configuration3_decision,
        load_verified_config3_detector_records,
    )
    from cobol_archaeologist.migration.agent import (
        validate_artifact_identity,
        validate_detector_evidence_binding,
    )

    decision, decision_sha256 = load_revalidate_configuration3_decision(
        output_dir=config3_output_dir,
        freeze=config3_freeze,
    )
    detector_active = decision.status == "GO"
    canonical_roster = load_canonical_roster(
        canonical_roster_path,
        review_evidence_root=review_evidence_root,
        protocol_root=protocol_root,
    )
    validation_protocol, validation_backend = _load_registered_validation_backend(
        protocol_root=protocol_root,
        cases=list(canonical_roster.cases),
    )

    request_by_case_track = {
        (request.case.case_id, request.track): request for request in requests
    }
    if len(request_by_case_track) != len(requests):
        raise ValueError("migration requests must be unique by case and track")
    case_by_id: dict[str, MigrationCase] = {
        case.case_id: case for case in canonical_roster.cases
    }
    if len(case_by_id) != len(canonical_roster.cases):
        raise ValueError("canonical roster case IDs must be unique")
    for request in requests:
        canonical = case_by_id.get(request.case.case_id)
        if canonical is None:
            raise ValueError("migration request names a case outside the canonical roster")
        if canonical != request.case:
            raise ValueError("migration request differs from its canonical roster case")
    active_tracks = (
        tuple(MigrationTrack)
        if detector_active
        else (MigrationTrack.ORACLE_ASSISTED,)
    )
    expected_request_keys = {
        (case_id, track) for case_id in case_by_id for track in active_tracks
    }
    if set(request_by_case_track) != expected_request_keys:
        if detector_active:
            raise ValueError("every reviewed case requires both separate track requests")
        raise ValueError(
            "inactive detector reporting requires exactly one oracle-assisted "
            "request per reviewed case and no detector-led requests"
        )
    detector_requests = [
        request for request in requests if request.track == MigrationTrack.DETECTOR_LED
    ]
    if detector_requests:
        detector_records, detector_records_sha256 = (
            load_verified_config3_detector_records(
                output_dir=config3_output_dir,
                freeze=config3_freeze,
            )
        )
        for request in detector_requests:
            validate_detector_evidence_binding(
                request,
                records=detector_records,
                records_sha256=detector_records_sha256,
            )
    artifact_by_key = {
        (artifact.run_key, artifact.track): artifact for artifact in artifacts
    }
    if len(artifact_by_key) != len(artifacts):
        raise ValueError("artifact run keys must be unique within each track")
    artifact_cases = {(artifact.case_id, artifact.track) for artifact in artifacts}
    if len(artifact_cases) != len(artifacts):
        raise ValueError("each case may have at most one scored artifact per track")
    for artifact in artifacts:
        if artifact.case_id not in case_by_id:
            raise ValueError(f"artifact names unknown roster case {artifact.case_id!r}")
        request = request_by_case_track.get((artifact.case_id, artifact.track))
        if request is None:
            raise ValueError("artifact has no matching reviewed track request")
        validate_artifact_identity(request, artifact)
    validations = _load_validation_artifacts(
        validation_pins,
        root=validation_evidence_root,
        request_by_case_track=request_by_case_track,
        artifact_by_key=artifact_by_key,
        canonical_source_root=canonical_source_root,
        backend=validation_backend,
        validation_protocol=validation_protocol,
    )

    reports: dict[MigrationTrack, TrackReport] = {}
    for track in MigrationTrack:
        track_active = track != MigrationTrack.DETECTOR_LED or detector_active
        track_artifacts = [
            artifact for artifact in artifacts if artifact.track == track
        ]
        track_validations = [
            validation for validation in validations if validation.track == track
        ]
        patched = [artifact for artifact in track_artifacts if not artifact.abstained]
        abstained = [artifact for artifact in track_artifacts if artifact.abstained]
        outcomes = Counter(validation.outcome for validation in track_validations)
        precisions = [
            validation.affected_line_precision
            for validation in track_validations
            if validation.affected_line_precision is not None
        ]
        reports[track] = TrackReport(
            eligible=(len(case_by_id) if track_active else 0),
            eligibility_status=(
                "eligible" if track_active else "ineligible_config3_decision"
            ),
            eligibility_reason=(
                None
                if track_active
                else "Detector-led migration is inactive because the pinned "
                f"configuration-3 decision is {decision.status}."
            ),
            evaluated=len(track_artifacts),
            patch_rate=_rate(len(patched), len(track_artifacts)),
            abstention_rate=_rate(len(abstained), len(track_artifacts)),
            apply_rate=_check_rate(
                track_validations, lambda check_id: check_id == "patch_apply"
            ),
            parse_rate=_check_rate(
                track_validations, lambda check_id: check_id == "parser"
            ),
            compile_rate=_check_rate(
                track_validations,
                lambda check_id: check_id == "compile" or check_id.endswith(":compile"),
            ),
            intended_test_rate=_check_rate(
                track_validations, lambda check_id: check_id == "intended_behavior"
            ),
            regression_rate=_check_rate(
                track_validations, lambda check_id: check_id.startswith("regression:")
            ),
            pass_rate=_rate(outcomes[CaseOutcome.PASS], len(track_validations)),
            by_drift_type=_breakdown(track_validations, case_by_id, "drift_type"),
            by_stratum=_breakdown(track_validations, case_by_id, "stratum"),
            by_capability=_breakdown(
                track_validations, case_by_id, "validation_capability"
            ),
            affected_line_precision_mean=(
                sum(precisions) / len(precisions) if precisions else None
            ),
            unrelated_change_count=sum(
                validation.unrelated_change_count for validation in track_validations
            ),
            total_turns=sum(artifact.usage.turns for artifact in track_artifacts),
            total_input_tokens=sum(
                artifact.usage.input_tokens for artifact in track_artifacts
            ),
            total_output_tokens=sum(
                artifact.usage.output_tokens for artifact in track_artifacts
            ),
            total_latency_ms=sum(
                artifact.usage.latency_ms for artifact in track_artifacts
            ),
            total_interruptions=sum(
                artifact.usage.interruptions for artifact in track_artifacts
            ),
            resumed_runs=sum(artifact.usage.resumed for artifact in track_artifacts),
            successful_case_ids=tuple(
                sorted(
                    validation.case_id
                    for validation in track_validations
                    if validation.outcome == CaseOutcome.PASS
                )
            ),
            failed_case_ids=tuple(
                sorted(
                    validation.case_id
                    for validation in track_validations
                    if validation.outcome == CaseOutcome.FAIL
                )
            ),
            abstained_case_ids=tuple(
                sorted(artifact.case_id for artifact in abstained)
            ),
        )

    detector_valid = detector_active and any(
        validation.track == MigrationTrack.DETECTOR_LED
        and validation.outcome == CaseOutcome.PASS
        for validation in validations
    )
    end_to_end = detector_active and detector_valid
    relationship = (
        "End-to-end migration evidence is supported by the detector utility gate "
        "and at least one valid detector-led patch."
        if end_to_end
        else "No end-to-end migration claim: both the detector utility gate and "
        "valid detector-led patch evidence are required; oracle-assisted results "
        "remain an upper-bound diagnostic."
    )
    return MigrationReport(
        roster_sha256=canonical_roster.roster_sha256,
        roster_case_ids=tuple(sorted(case_by_id)),
        tracks=reports,
        config3_decision_sha256=decision_sha256,
        config3_decision_status=decision.status,
        detector_utility_gate_passed=detector_active,
        detector_led_valid_patch_evidence=detector_valid,
        end_to_end_migration_claim_supported=end_to_end,
        release_relationship=relationship,
    )


def render_migration_report_markdown(report: MigrationReport) -> str:
    """Render the reconciled report without introducing a pooled headline."""

    lines = [
        "# T6 migration evaluation",
        "",
        f"Roster SHA-256: `{report.roster_sha256}`",
        (
            f"Configuration-3 decision: {report.config3_decision_status} "
            f"(`{report.config3_decision_sha256}`)"
        ),
        "",
        report.release_relationship,
        "",
    ]
    for track in MigrationTrack:
        result = report.tracks[track]
        lines.extend(
            [
                f"## {track.value.replace('_', ' ').title()}",
                "",
                f"Eligibility: {result.eligibility_status}",
                *(
                    [f"Eligibility reason: {result.eligibility_reason}"]
                    if result.eligibility_reason
                    else []
                ),
                f"Eligible/evaluated: {result.eligible}/{result.evaluated}",
                f"Patch rate: {_format_rate(result.patch_rate)}",
                f"Abstention rate: {_format_rate(result.abstention_rate)}",
                f"Apply rate: {_format_rate(result.apply_rate)}",
                f"Parse rate: {_format_rate(result.parse_rate)}",
                f"Compile rate: {_format_rate(result.compile_rate)}",
                f"Intended-test rate: {_format_rate(result.intended_test_rate)}",
                f"Regression rate: {_format_rate(result.regression_rate)}",
                f"Behavioral pass rate: {_format_rate(result.pass_rate)}",
                f"Unrelated changed lines: {result.unrelated_change_count}",
                f"Successful cases: {', '.join(result.successful_case_ids) or 'none'}",
                f"Failed cases: {', '.join(result.failed_case_ids) or 'none'}",
                f"Abstentions: {', '.join(result.abstained_case_ids) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines)


def _format_rate(rate: Rate) -> str:
    value = "n/a" if rate.value is None else f"{rate.value:.3f}"
    return f"{value} ({rate.passed}/{rate.denominator}; unavailable={rate.unavailable})"
