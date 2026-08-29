from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.migration.agent import (
    MIGRATION_SYSTEM_PROMPT,
    assert_track_authorized,
    build_migration_prompt,
    migration_run_key,
    stage_case_sources,
    validate_artifact_identity,
    validate_detector_evidence_binding,
)
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
    ValidationCapability,
)
from cobol_archaeologist.model.verify import VerificationResult
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


def _case(*, sha256: str | None = None) -> MigrationCase:
    return MigrationCase(
        case_id="migration_demo",
        instance_id="drift_000001",
        drift_type="D1_stale_threshold",
        stratum=CaseStratum.LOCAL,
        validation_capability=ValidationCapability.BATCH_EXECUTABLE,
        primary_program="DEMO",
        frozen_sources=(
            FrozenSource(
                path="programs/DEMO.cbl",
                sha256=sha256 or hashlib.sha256(SOURCE.encode()).hexdigest(),
            ),
        ),
        allowed_source_scope=(
            AllowedSourceScope(path="programs/DEMO.cbl", line_spans=((5, 5),)),
        ),
        intended_behavior=BehaviorCheck(
            check_id="new-display", description="prints the current mandated value"
        ),
        unaffected_regressions=(
            BehaviorCheck(check_id="clean-exit", description="still exits cleanly"),
        ),
        detector_input_ref="data/detector/demo.json",
        oracle_evidence_ref="data/oracle/demo.json",
        review_protocol_sha256="c" * 64,
        validation_protocol_sha256="d" * 64,
        review_state="human_primary_reviewed_and_verified",
        review_evidence_sha256="e" * 64,
        eligible_for_evaluation=True,
    )


def _prediction() -> DriftPrediction:
    return DriftPrediction(
        instance_id="drift_000001",
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
        drift_type="D1_stale_threshold",
        labels=Labels(
            program_level="drift",
            paragraph_level="drift",
            line_level=(SourceLineRef(program="DEMO", line=5),),
        ),
        rationale="The program prints the superseded value OLD.",
    )


def _request(track: MigrationTrack = MigrationTrack.DETECTOR_LED) -> MigrationRequest:
    return MigrationRequest(
        track=track,
        case=_case(),
        finding=MigrationFinding(
            origin=track,
            prediction=_prediction(),
            verifier_tier="static",
            verifier_evidence="DEMO line 5 contains literal OLD",
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


def _usage() -> RunUsage:
    return RunUsage(
        turns=1,
        input_tokens=100,
        output_tokens=20,
        latency_ms=200,
        interruptions=0,
        resumed=False,
    )


def test_prompt_locks_provider_and_excludes_hidden_roster_references() -> None:
    request = _request()
    prompt = build_migration_prompt(request)

    assert request.provider.model == "gpt-5.6-luna"
    assert request.provider.reasoning_effort == "max"
    assert request.provider.authentication == "chatgpt"
    assert "detector_input_ref" not in prompt
    assert "oracle_evidence_ref" not in prompt
    assert "data/oracle/demo.json" not in prompt
    assert "allowed_source_scope" not in prompt
    assert "unaffected_regressions" not in prompt
    assert "affected_hosts" not in prompt
    assert "one case" in MIGRATION_SYSTEM_PROMPT
    assert migration_run_key(request) == migration_run_key(request)

    oracle_prompt = build_migration_prompt(_request(MigrationTrack.ORACLE_ASSISTED))
    assert "allowed_source_scope" in oracle_prompt
    assert "unaffected_regressions" in oracle_prompt


def test_track_and_verified_finding_must_align() -> None:
    with pytest.raises(ValidationError, match="finding origin"):
        MigrationRequest(
            track=MigrationTrack.DETECTOR_LED,
            case=_case(),
            finding=MigrationFinding(
                origin=MigrationTrack.ORACLE_ASSISTED,
                prediction=_prediction(),
                verifier_tier="static",
                verifier_evidence="verified",
                evidence_ledger=("read",),
            ),
            method=_request().method,
        )


def _detector_record() -> EvaluationRecord:
    return EvaluationRecord.model_construct(
        instance_id="drift_000001",
        prediction=_prediction(),
        verification=VerificationResult(
            verified=True,
            tier=2,
            evidence="DEMO line 5 contains literal OLD",
            citation_ok=True,
            tier_attempts=[],
        ),
        system_id="adaptive_agent",
        run_key="config3-run",
        abstained=False,
        infrastructure_error=None,
    )


def _bound_detector_request(record: EvaluationRecord, records_sha256: str):
    request = _request(MigrationTrack.DETECTOR_LED)
    record_hash = hashlib.sha256(
        json.dumps(
            record.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return request.model_copy(
        update={
            "detector_evidence": DetectorEvidenceBinding(
                detector_records_sha256=records_sha256,
                evaluation_record_sha256=record_hash,
                evaluation_run_key=record.run_key,
            )
        }
    )


def test_detector_track_needs_canonically_revalidated_go(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cobol_archaeologist.eval import config3_live

    record = _detector_record()
    request = _bound_detector_request(record, "a" * 64)
    monkeypatch.setattr(
        config3_live,
        "load_revalidate_configuration3_decision",
        lambda **_: (Configuration3DecisionArtifact(status="NO_GO"), "b" * 64),
    )
    with pytest.raises(PermissionError, match="inactive"):
        assert_track_authorized(
            request,
            config3_output_dir=Path("canonical-config3"),
            config3_freeze=object(),
        )
    monkeypatch.setattr(
        config3_live,
        "load_revalidate_configuration3_decision",
        lambda **_: (Configuration3DecisionArtifact(status="GO"), "b" * 64),
    )
    monkeypatch.setattr(
        config3_live,
        "load_verified_config3_detector_records",
        lambda **_: ([record], "a" * 64),
    )
    assert_track_authorized(
        request,
        config3_output_dir=Path("canonical-config3"),
        config3_freeze=object(),
    )
    assert_track_authorized(
        _request(MigrationTrack.ORACLE_ASSISTED),
        config3_output_dir=Path("canonical-config3"),
        config3_freeze=object(),
    )


def test_oracle_prediction_cannot_be_relabelled_as_detector_evidence() -> None:
    record = _detector_record().model_copy(
        update={"prediction": _prediction().model_copy(update={"rationale": "other"})}
    )
    request = _bound_detector_request(record, "a" * 64)
    forged = request.model_copy(
        update={
            "finding": request.finding.model_copy(update={"prediction": _prediction()})
        }
    )

    with pytest.raises(ValueError, match="not the verified adaptive"):
        validate_detector_evidence_binding(
            forged,
            records=[record],
            records_sha256="a" * 64,
        )


def test_stage_case_sources_copies_only_hash_verified_files(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    source = canonical / "programs" / "DEMO.cbl"
    source.parent.mkdir(parents=True)
    source.write_text(SOURCE, encoding="utf-8", newline="")

    stage = stage_case_sources(
        _request(), canonical_root=canonical, staging_root=tmp_path / "staging"
    )

    assert stage != canonical
    assert (stage / "programs" / "DEMO.cbl").read_text(encoding="utf-8") == SOURCE
    assert source.read_text(encoding="utf-8") == SOURCE
    with pytest.raises(FileExistsError):
        stage_case_sources(
            _request(), canonical_root=canonical, staging_root=tmp_path / "staging"
        )


def test_stage_removes_partial_directory_after_hash_mismatch(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    source = canonical / "programs" / "DEMO.cbl"
    source.parent.mkdir(parents=True)
    source.write_text(SOURCE, encoding="utf-8", newline="")
    request = MigrationRequest(
        track=MigrationTrack.DETECTOR_LED,
        case=_case(sha256="0" * 64),
        finding=_request().finding,
        method=_request().method,
        detector_evidence=_request().detector_evidence,
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        stage_case_sources(
            request, canonical_root=canonical, staging_root=tmp_path / "staging"
        )
    run_key = migration_run_key(request)
    assert not (tmp_path / "staging" / run_key).exists()


def test_patch_artifact_requires_patch_or_explicit_abstention() -> None:
    run_key = "a" * 64
    with pytest.raises(ValidationError, match="requires a patch"):
        PatchArtifact(
            run_key=run_key,
            case_id="migration_demo",
            track=MigrationTrack.DETECTOR_LED,
            abstained=False,
            usage=_usage(),
        )

    abstention = PatchArtifact(
        run_key=run_key,
        case_id="migration_demo",
        track=MigrationTrack.DETECTOR_LED,
        abstained=True,
        abstention_reason="No safe local remediation is supported.",
        usage=_usage(),
    )
    assert abstention.patch is None

    patch = PatchArtifact(
        run_key=run_key,
        case_id="migration_demo",
        track=MigrationTrack.DETECTOR_LED,
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
            AffectedLocation(path="programs/DEMO.cbl", line_span=(5, 5)),
        ),
        abstained=False,
        usage=_usage(),
    )
    assert patch.affected_locations[0].line_span == (5, 5)


def test_artifact_identity_must_match_frozen_run_key_case_and_track() -> None:
    request = _request()
    artifact = PatchArtifact(
        run_key=migration_run_key(request),
        case_id=request.case.case_id,
        track=request.track,
        abstained=True,
        abstention_reason="No safe patch.",
        usage=_usage(),
    )
    validate_artifact_identity(request, artifact)

    mismatched = artifact.model_copy(update={"run_key": "f" * 64})
    with pytest.raises(ValueError, match="run key"):
        validate_artifact_identity(request, mismatched)


def test_run_key_binds_sources_runtime_cli_budget_and_track() -> None:
    base = _request()
    changed_source = MigrationRequest(
        track=base.track,
        case=_case(sha256="0" * 64),
        finding=base.finding,
        method=base.method,
        detector_evidence=base.detector_evidence,
    )
    changed_method = MigrationRequest(
        track=base.track,
        case=base.case,
        finding=base.finding,
        method=MigrationMethodIdentity(
            codex_cli_version="codex-cli 0.150.0",
            runner_sha256=base.method.runner_sha256,
            runtime_source_sha256=base.method.runtime_source_sha256,
            max_turns=base.method.max_turns,
            max_input_tokens=base.method.max_input_tokens,
            max_output_tokens=base.method.max_output_tokens,
        ),
        detector_evidence=base.detector_evidence,
    )
    oracle = _request(MigrationTrack.ORACLE_ASSISTED)

    assert migration_run_key(base) != migration_run_key(changed_source)
    assert migration_run_key(base) != migration_run_key(changed_method)
    assert migration_run_key(base) != migration_run_key(oracle)
