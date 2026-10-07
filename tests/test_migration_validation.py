from __future__ import annotations

import hashlib

from cobol_archaeologist.migration.agent import migration_run_key
from cobol_archaeologist.migration.contracts import (
    AffectedLocation,
    AllowedSourceScope,
    BehaviorCheck,
    CaseStratum,
    DetectorEvidenceBinding,
    FrozenSource,
    MigrationCase,
    MigrationFinding,
    MigrationMethodIdentity,
    MigrationRequest,
    MigrationTrack,
    PatchArtifact,
    RunUsage,
    ValidationCapability,
)
from cobol_archaeologist.migration.validate import (
    CaseOutcome,
    CheckObservation,
    CheckStatus,
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
