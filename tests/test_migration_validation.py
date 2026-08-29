from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cobol_archaeologist.migration.agent import migration_run_key
from cobol_archaeologist.migration.contracts import (
    AffectedLocation,
    AllowedSourceScope,
    BehaviorCheck,
    CaseStratum,
    Configuration3DecisionArtifact,
    DetectorEvidenceBinding,
    FrozenSource,
    MigrationCase,
    MigrationFinding,
    MigrationMethodIdentity,
    MigrationRequest,
    MigrationTrack,
    PatchArtifact,
    RunUsage,
    ValidationArtifactPin,
    ValidationCapability,
)
from cobol_archaeologist.migration.report import (
    build_migration_report,
    migration_validator_sha256,
    render_migration_report_markdown,
    validation_backend_sha256,
)
from cobol_archaeologist.migration.validate import (
    CaseOutcome,
    CheckObservation,
    CheckStatus,
    MigrationValidation,
    validate_migration,
)
from cobol_archaeologist.schemas import (
    CodeLocus,
    CurrentValue,
    DriftPrediction,
    Labels,
    RegulationClause,
    SourceLineRef,
    SourceLocus,
)

SOURCE = """IDENTIFICATION DIVISION.
PROGRAM-ID. DEMO.
PROCEDURE DIVISION.
MAIN.
    DISPLAY \"OLD\".
    STOP RUN.
"""


class PassingBackend:
    def __init__(self) -> None:
        self.compile_hosts: list[str | None] = []
        self.static_hosts: list[str | None] = []

    def parse(self, case, files):
        return CheckObservation(check_id="parser", status="pass", log="parsed")

    def static(self, case, files, *, host=None):
        self.static_hosts.append(host)
        ids = (
            "call_graph",
            "dataflow",
            "slice",
            "source_locus",
            "unresolved_references",
            "verifier_conflicts",
        )
        return tuple(
            CheckObservation(check_id=check_id, status="pass", log="clean")
            for check_id in ids
        )

    def compile(self, case, files, *, host=None):
        self.compile_hosts.append(host)
        return CheckObservation(check_id="compile", status="pass", log="compiled")

    def behavior(self, case, files, check):
        return CheckObservation(check_id=check.check_id, status="pass", log="passed")


def _case(
    capability: ValidationCapability = ValidationCapability.BATCH_EXECUTABLE,
    *,
    scope: tuple[int, int] = (5, 5),
) -> MigrationCase:
    return MigrationCase(
        case_id=f"migration_{capability.value}",
        instance_id="drift_000001",
        drift_type="D1_stale_threshold",
        stratum=CaseStratum.LOCAL,
        validation_capability=capability,
        primary_program="DEMO",
        frozen_sources=(
            FrozenSource(
                path="programs/DEMO.cbl",
                sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
            ),
        ),
        allowed_source_scope=(
            AllowedSourceScope(path="programs/DEMO.cbl", line_spans=(scope,)),
        ),
        intended_behavior=BehaviorCheck(
            check_id="new-display", description="prints NEW"
        ),
        unaffected_regressions=(
            BehaviorCheck(check_id="clean-exit", description="exits cleanly"),
        ),
        affected_hosts=("HOST1", "HOST2")
        if capability == ValidationCapability.COPYBOOK_FANOUT
        else (),
        detector_input_ref="detector/demo.json",
        oracle_evidence_ref="oracle/demo.json",
        review_protocol_sha256="c" * 64,
        validation_protocol_sha256="d" * 64,
        review_state="human_primary_reviewed_and_verified",
        review_evidence_sha256="e" * 64,
        eligible_for_evaluation=True,
    )


def _request(
    case: MigrationCase,
    track: MigrationTrack = MigrationTrack.DETECTOR_LED,
) -> MigrationRequest:
    prediction = DriftPrediction(
        instance_id=case.instance_id,
        regulation_clause=RegulationClause(
            doc="Demo Direction",
            clause_id="1",
            version="2026",
            effective_date="2026-01-01",
            text="The program must print NEW.",
            current_value=CurrentValue(kind="enum", value="NEW", comparator="equal"),
        ),
        code_locus=CodeLocus(
            loci=(SourceLocus(program="DEMO", paragraph="MAIN", line_span=(5, 5)),),
            slice_vars=(),
            is_interprocedural=False,
        ),
        drift_type=case.drift_type,
        labels=Labels(
            program_level="drift",
            paragraph_level="drift",
            line_level=(SourceLineRef(program="DEMO", line=5),),
        ),
        rationale="The source retains the superseded value.",
    )
    return MigrationRequest(
        track=track,
        case=case,
        finding=MigrationFinding(
            origin=track,
            prediction=prediction,
            verifier_tier="static",
            verifier_evidence="verified line-level evidence",
            evidence_ledger=("read_paragraph(DEMO, MAIN)",),
        ),
        method=MigrationMethodIdentity(
            codex_cli_version="codex-cli 0.149.0",
            runner_sha256="1" * 64,
            runtime_source_sha256="2" * 64,
            max_turns=16,
            max_input_tokens=98_304,
            max_output_tokens=16_384,
        ),
        detector_evidence=(
            DetectorEvidenceBinding(
                detector_records_sha256="3" * 64,
                evaluation_record_sha256="4" * 64,
                evaluation_run_key="config3-run",
            )
            if track == MigrationTrack.DETECTOR_LED
            else None
        ),
    )


def _usage(*, resumed: bool = False) -> RunUsage:
    return RunUsage(
        turns=2,
        input_tokens=100,
        output_tokens=20,
        latency_ms=300,
        interruptions=int(resumed),
        resumed=resumed,
    )


def _report_context(
    tmp_path: Path,
    case: MigrationCase,
    *,
    decision_status: str,
):
    def write_json(relative: str, payload: dict) -> dict[str, str]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        path.write_bytes(raw)
        return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}

    source_path = tmp_path / "review-source.txt"
    source_path.write_text("independently reviewed migration evidence", encoding="utf-8")
    source_pin = {
        "path": "review-source.txt",
        "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    }
    response_pins: dict[str, dict[str, str]] = {}
    verification_pins: dict[str, dict[str, str]] = {}
    public_keys: dict[str, str] = {}
    for index, (role, reviewer) in enumerate((
        ("human_primary", "primary-a"),
        ("independent_verifier", "verifier-b"),
        ("adjudicator", "adjudicator-c"),
    ), start=1):
        response_pin = write_json(
            f"review-responses/{role}.json",
            {
                "schema_version": "migration-review-response-v1",
                "case_id": case.case_id,
                "instance_id": case.instance_id,
                "review_role": role,
                "reviewer_identity": reviewer,
                "completed_at": "2026-08-24T10:00:00Z",
                "decision": "include",
                "rationale": f"{role} independently included the case.",
                "evidence": [source_pin],
            },
        )
        response_pins[role] = response_pin
        private_key = Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)
        public_keys[reviewer] = private_key.public_key().public_bytes_raw().hex()
        verification = {
            "schema_version": "migration-reviewer-verification-v1",
            "review_role": role,
            "reviewer_identity": reviewer,
            "response": response_pin,
            "identity_verified": True,
            "human_reviewer_verified": True,
            "verified_by_external_party": "external-review-office",
            "verification_method": "signed reviewer roster",
            "evidence_reference": f"registry:{reviewer}",
            "verified_at": "2026-08-24T11:00:00Z",
        }
        signed = json.dumps(
            verification, sort_keys=True, separators=(",", ":")
        ).encode()
        verification["signature_ed25519"] = private_key.sign(signed).hex()
        verification_pins[role] = write_json(
            f"review-identities/{role}.json",
            verification,
        )
    evidence = json.dumps(
        {
            "schema_version": "migration-review-evidence-v1",
            "case_id": case.case_id,
            "instance_id": case.instance_id,
            "human_primary_response": response_pins["human_primary"],
            "independent_verifier_response": response_pins[
                "independent_verifier"
            ],
            "adjudication_response": response_pins["adjudicator"],
            "human_primary_identity_verification": verification_pins[
                "human_primary"
            ],
            "independent_verifier_identity_verification": verification_pins[
                "independent_verifier"
            ],
            "adjudicator_identity_verification": verification_pins["adjudicator"],
            "review_state": "human_primary_reviewed_and_verified",
            "eligible_for_evaluation": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    review_protocol = json.dumps(
        {
            "schema_version": "migration-review-protocol-v1",
            "state": "ready",
            "frozen_before_responses": True,
            "frozen_at": "2026-08-24T09:00:00Z",
            "runtime_source_sha256": "2" * 64,
            "reviewer_keys": [
                {
                    "review_role": role,
                    "reviewer_identity": reviewer,
                    "key_id": f"{role}-key",
                    "public_key_ed25519": public_keys[reviewer],
                }
                for role, reviewer in (
                    ("human_primary", "primary-a"),
                    ("independent_verifier", "verifier-b"),
                    ("adjudicator", "adjudicator-c"),
                )
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (tmp_path / "review-protocol.json").write_bytes(review_protocol)
    backend = PassingBackend()
    validation_protocol = json.dumps(
        {
            "schema_version": "migration-validation-protocol-v1",
            "state": "ready",
            "frozen_before_runs": True,
            "frozen_at": "2026-08-24T09:00:00Z",
            "runtime_source_sha256": "2" * 64,
            "validator_sha256": migration_validator_sha256(),
            "backend_id": "test-passing-backend-v1",
            "backend_module": type(backend).__module__,
            "backend_qualname": type(backend).__qualname__,
            "backend_sha256": validation_backend_sha256(backend),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (tmp_path / "validation-protocol.json").write_bytes(validation_protocol)
    case = case.model_copy(
        update={
            "review_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "review_protocol_sha256": hashlib.sha256(review_protocol).hexdigest(),
            "validation_protocol_sha256": hashlib.sha256(
                validation_protocol
            ).hexdigest(),
        }
    )
    review_path = tmp_path / f"{case.case_id}.json"
    review_path.write_bytes(evidence)
    roster_path = tmp_path / "cases.jsonl"
    roster_path.write_text(case.model_dump_json() + "\n", encoding="utf-8")

    decision_raw = json.dumps(
        {
            "schema_version": "configuration-3-decision-v1",
            "configuration": 3,
            "status": decision_status,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    decision_path = tmp_path / "config3-decision.json"
    decision_path.write_bytes(decision_raw)
    return (
        case,
        roster_path,
        decision_path,
        hashlib.sha256(decision_raw).hexdigest(),
        public_keys,
    )


def _model_hash(model) -> str:
    raw = json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _validation_pin(
    root: Path,
    validation,
    request: MigrationRequest,
    artifact: PatchArtifact,
    backend,
) -> ValidationArtifactPin:
    relative = f"validations/{validation.run_key}-{validation.track.value}.json"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = validation.model_dump_json().encode()
    path.write_bytes(raw)
    return ValidationArtifactPin(
        path=relative,
        sha256=hashlib.sha256(raw).hexdigest(),
        request_sha256=_model_hash(request),
        artifact_sha256=_model_hash(artifact),
        validator_sha256=migration_validator_sha256(),
        backend_sha256=validation_backend_sha256(backend),
        runtime_source_sha256=request.method.runtime_source_sha256,
        run_key=validation.run_key,
        case_id=validation.case_id,
        track=validation.track,
    )


def _write_canonical_source(root: Path) -> Path:
    canonical = root / "canonical-source"
    source = canonical / "programs" / "DEMO.cbl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(SOURCE, encoding="utf-8", newline="")
    return canonical


def _artifact(
    case: MigrationCase,
    *,
    track: MigrationTrack = MigrationTrack.DETECTOR_LED,
    affected_line: int = 5,
) -> PatchArtifact:
    request = _request(case, track)
    return PatchArtifact(
        run_key=migration_run_key(request),
        case_id=case.case_id,
        track=track,
        patch=(
            "--- a/programs/DEMO.cbl\n"
            "+++ b/programs/DEMO.cbl\n"
            "@@ -5,1 +5,1 @@\n"
            '-    DISPLAY "OLD".\n'
            '+    DISPLAY "NEW".\n'
        ),
        rationale="Replace the stale literal.",
        intended_behavior="Print NEW.",
        affected_locations=(
            AffectedLocation(
                path="programs/DEMO.cbl", line_span=(affected_line, affected_line)
            ),
        ),
        abstained=False,
        usage=_usage(),
    )


def test_batch_patch_passes_all_required_gates() -> None:
    case = _case()
    backend = PassingBackend()
    result = validate_migration(
        _request(case),
        _artifact(case),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=backend,
    )

    assert result.outcome == CaseOutcome.PASS
    assert result.changed_files == ("programs/DEMO.cbl",)
    assert result.changed_line_count == 1
    assert result.affected_line_precision == 1.0
    assert backend.compile_hosts == [None]
    assert {check.check_id for check in result.checks} >= {
        "frozen_source_hash",
        "patch_apply",
        "allowed_source_scope",
        "parser",
        "compile",
        "intended_behavior",
        "regression:clean-exit",
    }


def test_out_of_scope_patch_is_retained_as_failure() -> None:
    case = _case(scope=(1, 4))
    result = validate_migration(
        _request(case),
        _artifact(case),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=PassingBackend(),
    )

    assert result.outcome == CaseOutcome.FAIL
    assert result.unrelated_change_count == 1
    assert any(
        check.check_id == "allowed_source_scope" and check.status == CheckStatus.FAIL
        for check in result.checks
    )


def test_reported_affected_locations_must_also_stay_in_scope() -> None:
    case = _case()
    result = validate_migration(
        _request(case),
        _artifact(case, affected_line=4),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=PassingBackend(),
    )

    assert result.outcome == CaseOutcome.FAIL
    assert result.unrelated_change_count == 0
    assert any(
        check.check_id == "affected_locations" and "exceed the allowlist" in check.log
        for check in result.checks
    )


def test_noop_patch_is_rejected_before_validation_backend_runs() -> None:
    case = _case()
    artifact = _artifact(case).model_copy(
        update={
            "patch": (
                "--- a/programs/DEMO.cbl\n"
                "+++ b/programs/DEMO.cbl\n"
                "@@ -5,1 +5,1 @@\n"
                '-    DISPLAY "OLD".\n'
                '+    DISPLAY "OLD".\n'
            )
        }
    )
    result = validate_migration(
        _request(case),
        artifact,
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=PassingBackend(),
    )

    assert result.outcome == CaseOutcome.FAIL
    assert any(
        check.check_id == "patch_apply" and "no source change" in check.log
        for check in result.checks
    )


def test_cics_reports_compile_unavailable_and_requires_static_evidence() -> None:
    case = _case(ValidationCapability.CICS_STATIC)
    backend = PassingBackend()
    result = validate_migration(
        _request(case),
        _artifact(case),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=backend,
    )

    assert result.outcome == CaseOutcome.PASS
    assert backend.compile_hosts == []
    compile_check = next(
        check for check in result.checks if check.check_id == "compile"
    )
    assert compile_check.status == CheckStatus.UNAVAILABLE
    assert "CICS" in compile_check.log


def test_copybook_validation_fans_out_across_every_host() -> None:
    case = _case(ValidationCapability.COPYBOOK_FANOUT)
    backend = PassingBackend()
    result = validate_migration(
        _request(case),
        _artifact(case),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=backend,
    )

    assert result.outcome == CaseOutcome.PASS
    assert backend.compile_hosts == ["HOST1", "HOST2"]
    assert backend.static_hosts == ["HOST1", "HOST2"]
    assert {check.check_id for check in result.checks} >= {
        "host:HOST1:compile",
        "host:HOST2:compile",
    }


def test_missing_mandatory_static_check_is_a_failure() -> None:
    class IncompleteBackend(PassingBackend):
        def static(self, case, files, *, host=None):
            return (CheckObservation(check_id="dataflow", status="pass", log="ok"),)

    case = _case()
    result = validate_migration(
        _request(case),
        _artifact(case),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=IncompleteBackend(),
    )

    assert result.outcome == CaseOutcome.FAIL
    assert any(
        check.check_id == "unresolved_references" and check.status == CheckStatus.FAIL
        for check in result.checks
    )


def test_backend_exception_is_retained_as_failure_log() -> None:
    class BrokenBackend(PassingBackend):
        def behavior(self, case, files, check):
            raise RuntimeError("fixture crashed")

    case = _case()
    result = validate_migration(
        _request(case),
        _artifact(case),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=BrokenBackend(),
    )

    assert result.outcome == CaseOutcome.FAIL
    assert any("fixture crashed" in check.log for check in result.checks)


def test_backend_cannot_relabel_the_wrong_behavior_check_as_a_pass() -> None:
    class WrongCheckBackend(PassingBackend):
        def behavior(self, case, files, check):
            return CheckObservation(
                check_id="different-check", status="pass", log="wrong fixture"
            )

    case = _case()
    result = validate_migration(
        _request(case),
        _artifact(case),
        expected_track=MigrationTrack.DETECTOR_LED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=WrongCheckBackend(),
    )

    assert result.outcome == CaseOutcome.FAIL
    assert any("unexpected check ID" in check.log for check in result.checks)


def test_report_never_pools_oracle_only_results_after_detector_no_go(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cobol_archaeologist.eval import config3_live

    case, roster_path, _, _, _public_keys = _report_context(
        tmp_path, _case(), decision_status="NO_GO"
    )
    monkeypatch.setattr(
        config3_live,
        "load_revalidate_configuration3_decision",
        lambda **_: (Configuration3DecisionArtifact(status="NO_GO"), "d" * 64),
    )
    oracle = _artifact(case, track=MigrationTrack.ORACLE_ASSISTED)
    backend = PassingBackend()
    oracle_request = _request(case, MigrationTrack.ORACLE_ASSISTED)
    oracle_validation = validate_migration(
        oracle_request,
        oracle,
        expected_track=MigrationTrack.ORACLE_ASSISTED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=backend,
    )

    report = build_migration_report(
        [oracle_request],
        [oracle],
        [_validation_pin(tmp_path, oracle_validation, oracle_request, oracle, backend)],
        validation_evidence_root=tmp_path,
        canonical_source_root=_write_canonical_source(tmp_path),
        canonical_roster_path=roster_path,
        review_evidence_root=tmp_path,
        protocol_root=tmp_path,
        config3_output_dir=tmp_path / "config3",
        config3_freeze=object(),
    )

    assert set(report.tracks) == {
        MigrationTrack.DETECTOR_LED,
        MigrationTrack.ORACLE_ASSISTED,
    }
    detector_report = report.tracks[MigrationTrack.DETECTOR_LED]
    assert detector_report.eligible == 0
    assert detector_report.evaluated == 0
    assert detector_report.eligibility_status == "ineligible_config3_decision"
    assert detector_report.pass_rate.denominator == 0
    assert detector_report.pass_rate.value is None
    assert report.tracks[MigrationTrack.ORACLE_ASSISTED].evaluated == 1
    assert not report.detector_led_valid_patch_evidence
    assert not report.end_to_end_migration_claim_supported
    assert report.oracle_assisted_is_upper_bound_only
    assert "oracle-assisted" in report.release_relationship
    assert len(report.roster_sha256) == 64
    narrative = render_migration_report_markdown(report)
    assert "Detector Led" in narrative
    assert "Oracle Assisted" in narrative


def test_report_refuses_missing_track_or_unbound_artifact_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cobol_archaeologist.eval import config3_live

    case, roster_path, _, _, _public_keys = _report_context(
        tmp_path, _case(), decision_status="GO"
    )
    monkeypatch.setattr(
        config3_live,
        "load_revalidate_configuration3_decision",
        lambda **_: (Configuration3DecisionArtifact(status="GO"), "d" * 64),
    )
    detector_request = _request(case, MigrationTrack.DETECTOR_LED)
    oracle_request = _request(case, MigrationTrack.ORACLE_ASSISTED)

    with pytest.raises(ValueError, match="both separate track requests"):
        build_migration_report(
            [detector_request],
            [],
            [],
            validation_evidence_root=tmp_path,
            canonical_source_root=_write_canonical_source(tmp_path),
            canonical_roster_path=roster_path,
            review_evidence_root=tmp_path,
            protocol_root=tmp_path,
            config3_output_dir=tmp_path / "config3",
            config3_freeze=object(),
        )

    case, roster_path, _, _, _public_keys = _report_context(
        tmp_path, _case(), decision_status="NO_GO"
    )
    monkeypatch.setattr(
        config3_live,
        "load_revalidate_configuration3_decision",
        lambda **_: (Configuration3DecisionArtifact(status="NO_GO"), "d" * 64),
    )
    oracle_request = _request(case, MigrationTrack.ORACLE_ASSISTED)
    oracle = _artifact(case, track=MigrationTrack.ORACLE_ASSISTED)
    forged = oracle.model_copy(update={"run_key": "f" * 64})
    with pytest.raises(ValueError, match="run key"):
        build_migration_report(
            [oracle_request],
            [forged],
            [],
            validation_evidence_root=tmp_path,
            canonical_source_root=_write_canonical_source(tmp_path),
            canonical_roster_path=roster_path,
            review_evidence_root=tmp_path,
            protocol_root=tmp_path,
            config3_output_dir=tmp_path / "config3",
            config3_freeze=object(),
        )


def test_report_refuses_hash_pinned_but_forged_empty_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cobol_archaeologist.eval import config3_live

    case, roster_path, _, _, _public_keys = _report_context(
        tmp_path, _case(), decision_status="NO_GO"
    )
    monkeypatch.setattr(
        config3_live,
        "load_revalidate_configuration3_decision",
        lambda **_: (Configuration3DecisionArtifact(status="NO_GO"), "d" * 64),
    )
    request = _request(case, MigrationTrack.ORACLE_ASSISTED)
    artifact = _artifact(case, track=MigrationTrack.ORACLE_ASSISTED)
    forged = MigrationValidation(
        run_key=artifact.run_key,
        case_id=case.case_id,
        track=MigrationTrack.ORACLE_ASSISTED,
        capability=case.validation_capability,
        outcome=CaseOutcome.PASS,
        checks=(),
    )
    backend = PassingBackend()
    pin = _validation_pin(tmp_path, forged, request, artifact, backend)

    with pytest.raises(ValueError, match="missing required checks"):
        build_migration_report(
            [request],
            [artifact],
            [pin],
            validation_evidence_root=tmp_path,
            canonical_source_root=_write_canonical_source(tmp_path),
            canonical_roster_path=roster_path,
            review_evidence_root=tmp_path,
            protocol_root=tmp_path,
            config3_output_dir=tmp_path / "config3",
            config3_freeze=object(),
        )


def test_report_replays_and_rejects_complete_hand_authored_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cobol_archaeologist.eval import config3_live

    case, roster_path, _, _, _public_keys = _report_context(
        tmp_path, _case(), decision_status="NO_GO"
    )
    monkeypatch.setattr(
        config3_live,
        "load_revalidate_configuration3_decision",
        lambda **_: (Configuration3DecisionArtifact(status="NO_GO"), "d" * 64),
    )
    request = _request(case, MigrationTrack.ORACLE_ASSISTED)
    artifact = _artifact(case, track=MigrationTrack.ORACLE_ASSISTED)
    backend = PassingBackend()
    legitimate = validate_migration(
        request,
        artifact,
        expected_track=MigrationTrack.ORACLE_ASSISTED,
        base_files={"programs/DEMO.cbl": SOURCE},
        backend=backend,
    )
    forged = legitimate.model_copy(update={"changed_line_count": 99})
    pin = _validation_pin(tmp_path, forged, request, artifact, backend)

    with pytest.raises(ValueError, match="deterministic validator replay"):
        build_migration_report(
            [request],
            [artifact],
            [pin],
            validation_evidence_root=tmp_path,
            canonical_source_root=_write_canonical_source(tmp_path),
            canonical_roster_path=roster_path,
            review_evidence_root=tmp_path,
            protocol_root=tmp_path,
            config3_output_dir=tmp_path / "config3",
            config3_freeze=object(),
        )
