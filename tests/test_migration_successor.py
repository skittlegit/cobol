"""Additive successor requests never weaken historical migration contracts."""

import hashlib
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from cobol_archaeologist.migration.ai_review import AICanonicalMigrationCase
from cobol_archaeologist.migration.contracts import MigrationCase
from cobol_archaeologist.migration.successor import (
    MigrationProposal,
    SuccessorCapture,
    SuccessorMigrationRequest,
    build_successor_prompt,
    capture_successor_final,
    replay_successor_capture,
    stage_successor_sources,
    successor_run_key,
    successor_schema_hashes,
    validate_configuration4_binding,
    validate_successor_migration,
)
from cobol_archaeologist.migration.validate import CaseOutcome, CheckObservation

SOURCE = "PROCEDURE DIVISION.\n    DISPLAY 1.\n    STOP RUN.\n"


def request():
    case = AICanonicalMigrationCase(
        case_id="migration_demo",
        instance_id="drift_000001",
        drift_type="D1_stale_threshold",
        stratum="local",
        validation_capability="batch_executable",
        primary_program="DEMO",
        frozen_sources=[
            {"path": "DEMO.cbl", "sha256": hashlib.sha256(SOURCE.encode()).hexdigest()}
        ],
        source_evidence=[
            {
                "path": "evidence/DEMO.cbl",
                "sha256": hashlib.sha256(SOURCE.encode()).hexdigest(),
            }
        ],
        regulation_evidence={"path": "regulation.json", "sha256": "a" * 64},
        fixture_evidence=[{"path": "fixtures.json", "sha256": "b" * 64}],
        allowed_source_scope=[{"path": "DEMO.cbl", "line_spans": [[2, 2]]}],
        intended_behavior={"check_id": "intended", "description": "display 2"},
        unaffected_regressions=[{"check_id": "unchanged", "description": "terminate"}],
        detector_input_ref="private/detector.json",
        oracle_evidence_ref="private/oracle.json",
        validation_protocol_sha256="c" * 64,
        source_bundle_group="group",
        duplicate_source_justification="unique",
        review_protocol_sha256="d" * 64,
        review_evidence_sha256="e" * 64,
        review_evidence={"path": "private/reviews.json", "sha256": "e" * 64},
    )
    return SuccessorMigrationRequest(
        case=case,
        finding={
            "origin": "oracle_assisted",
            "prediction": {
                "instance_id": "drift_000001",
                "drift_type": "D1_stale_threshold",
                "regulation_clause": {
                    "doc": "Demo Direction",
                    "clause_id": "1",
                    "version": "2026",
                    "effective_date": "2026-01-01",
                    "text": "Display 2",
                    "current_value": {
                        "kind": "numeric",
                        "value": 2,
                        "comparator": "equal",
                    },
                },
                "code_locus": {
                    "loci": [
                        {"program": "DEMO", "paragraph": "MAIN", "line_span": [2, 2]}
                    ],
                    "slice_vars": [],
                    "is_interprocedural": False,
                },
                "labels": {
                    "program_level": "drift",
                    "paragraph_level": "drift",
                    "line_level": [{"program": "DEMO", "line": 2}],
                },
                "rationale": "threshold is stale",
            },
            "verifier_tier": "static",
            "verifier_evidence": "reviewed source",
            "evidence_ledger": ["approved finding"],
        },
        detector={
            "evaluation_manifest": {"path": "eval.json", "sha256": "1" * 64},
            "detector_decision": {"path": "decision.json", "sha256": "2" * 64},
            "input_roster": {"path": "roster.json", "sha256": "3" * 64},
        },
        method={
            "codex_cli_version": "test",
            "runner_sha256": "4" * 64,
            "runtime_source_sha256": "5" * 64,
            "validator_sha256": "6" * 64,
            "backend_sha256": "7" * 64,
            "validation_protocol_sha256": "c" * 64,
            "max_turns": 10,
            "max_input_tokens": 1000,
            "max_output_tokens": 1000,
        },
        schema_sha256=successor_schema_hashes(),
    )


def proposal():
    return {
        "kind": "patch",
        "patch": "--- a/DEMO.cbl\n+++ b/DEMO.cbl\n@@ -2 +2 @@\n-    DISPLAY 1.\n+    DISPLAY 2.\n",
        "rationale": "update stale threshold",
        "intended_behavior": "display 2",
        "affected_locations": [{"path": "DEMO.cbl", "line_span": [2, 2]}],
    }


def capture(req, final):
    return capture_successor_final(
        req,
        json.dumps(final).encode(),
        task_id="task",
        session_id="session",
        started_at="2026-10-06T00:00:00Z",
        completed_at="2026-10-06T01:00:00Z",
        host_events={"path": "events.json", "sha256": "8" * 64},
        raw_transcript={"path": "transcript.txt", "sha256": "9" * 64},
    )


def test_successor_one_case_visible_and_historical_contract_separate():
    req = request()
    prompt = build_successor_prompt(req)
    assert "oracle_assisted" in prompt and "DISPLAY" not in prompt
    assert "allowed_source_scope" in prompt and "unaffected_regressions" in prompt
    assert "private/" not in prompt and "fixture_evidence" not in prompt
    assert "review_evidence" not in prompt and "detector_decision" not in prompt
    assert req.provider.model == "gpt-6-luna" and req.provider.reasoning_effort == "max"
    with pytest.raises(ValidationError):
        MigrationCase.model_validate(req.case.model_dump())


@pytest.mark.parametrize(
    "field,value", [("track", "detector_led"), ("provider", {"model": "gpt-6.1-sol"})]
)
def test_reject_unapproved_track_and_provider(field, value):
    raw = request().model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        SuccessorMigrationRequest.model_validate(raw)


def test_request_bindings_and_run_key():
    req = request()
    raw = req.model_dump(mode="json")
    raw["schema_sha256"]["response"] = "f" * 64
    with pytest.raises(ValidationError, match="schema"):
        SuccessorMigrationRequest.model_validate(raw)
    for section, field in [
        ("method", "runtime_source_sha256"),
        ("case", "allowed_source_scope"),
    ]:
        raw = req.model_dump(mode="json")
        raw[section][field] = (
            "f" * 64
            if section == "method"
            else [{"path": "DEMO.cbl", "line_spans": [[1, 2]]}]
        )
        assert successor_run_key(
            SuccessorMigrationRequest.model_validate(raw)
        ) != successor_run_key(req)
    raw = req.model_dump(mode="json")
    raw["detector"]["eligible_findings"] = 1
    with pytest.raises(ValidationError):
        SuccessorMigrationRequest.model_validate(raw)
    raw = req.model_dump(mode="json")
    raw["method"]["validation_protocol_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="protocol"):
        SuccessorMigrationRequest.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    ["usage", "run_key", "case_id", "provider", "host_events", "abstention_reason"],
)
def test_model_cannot_author_host_fields(field):
    raw = proposal()
    raw[field] = "invented"
    with pytest.raises(ValidationError):
        TypeAdapter(MigrationProposal).validate_python(raw)


def test_capture_no_fabricated_provider_usage():
    req = request()
    artifact = capture(req, proposal())
    assert artifact.provider_usage == "not_recorded"
    assert artifact.run_key == successor_run_key(req)
    assert artifact.provider == req.provider
    assert (
        artifact.exact_final_sha256
        == hashlib.sha256(json.dumps(proposal()).encode()).hexdigest()
    )
    assert "usage" not in artifact.proposal.model_dump()
    raw = artifact.model_dump(mode="json")
    raw["run_key"] = "f" * 64
    altered = SuccessorCapture.model_validate(raw)
    with pytest.raises(ValueError, match="identity"):
        validate_successor_migration(
            req, altered, base_files={"DEMO.cbl": SOURCE}, backend=Backend()
        )


class Backend:
    def parse(self, case, files):
        assert isinstance(case, AICanonicalMigrationCase)
        assert "DISPLAY 2" in files["DEMO.cbl"]
        return CheckObservation(check_id="parser", status="pass", log="test backend")

    def static(self, case, files, *, host=None):
        return tuple(
            CheckObservation(check_id=name, status="pass", log="test backend")
            for name in ("unresolved_references", "verifier_conflicts")
        )

    def compile(self, case, files, *, host=None):
        return CheckObservation(check_id="compile", status="pass", log="test backend")

    def behavior(self, case, files, check):
        return CheckObservation(
            check_id=check.check_id, status="pass", log="test backend"
        )


def test_reuses_patch_validation_with_ai_case():
    req = request()
    artifact = capture(req, proposal())
    result = validate_successor_migration(
        req, artifact, base_files={"DEMO.cbl": SOURCE}, backend=Backend()
    )
    assert result.outcome == CaseOutcome.PASS
    assert result.run_key == successor_run_key(req)
    assert result.changed_line_count == 1
    result = validate_successor_migration(
        req, artifact, base_files={"DEMO.cbl": "wrong"}, backend=Backend()
    )
    assert result.outcome == CaseOutcome.FAIL
    assert result.checks[0].check_id == "frozen_source_hash"
    raw = proposal()
    raw["patch"] = (
        raw["patch"].replace("-2 +2", "-3 +3").replace("DISPLAY 1.", "STOP RUN.")
    )
    result = validate_successor_migration(
        req, capture(req, raw), base_files={"DEMO.cbl": SOURCE}, backend=Backend()
    )
    assert result.outcome == CaseOutcome.FAIL
    assert any(
        c.check_id == "allowed_source_scope" and c.status == "fail"
        for c in result.checks
    )


def test_abstention_and_source_staging(tmp_path):
    req = request()
    artifact = capture(req, {"kind": "abstention", "reason": "cannot safely remediate"})
    result = validate_successor_migration(
        req, artifact, base_files={}, backend=Backend()
    )
    assert result.outcome == CaseOutcome.ABSTENTION
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "DEMO.cbl").write_bytes(SOURCE.encode())
    staged = stage_successor_sources(
        req, canonical_root=canonical, staging_root=tmp_path / "staging"
    )
    assert staged.name == successor_run_key(req)
    assert [p.name for p in staged.iterdir()] == ["DEMO.cbl"]
    with pytest.raises(FileExistsError):
        stage_successor_sources(
            req, canonical_root=canonical, staging_root=tmp_path / "staging"
        )
    (canonical / "DEMO.cbl").write_bytes(b"wrong")
    with pytest.raises(ValueError, match="hash"):
        stage_successor_sources(
            req, canonical_root=canonical, staging_root=tmp_path / "failed"
        )
    assert not list((tmp_path / "failed").iterdir())


def test_pinned_detector_intake_and_capture_replay(tmp_path):
    def pin(name, value):
        raw = json.dumps(value).encode()
        (tmp_path / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    req = request()
    decision = pin(
        "decision.json",
        {
            "schema_version": "configuration-4-detector-decision-v1",
            "configuration": 4,
            "status": "NOT_EVALUABLE",
        },
    )
    roster = pin(
        "roster.json",
        {
            "configuration": 4,
            "decision": decision,
            "detector_led": {"active": False, "count": 0, "eligible_findings": []},
        },
    )
    raw = req.model_dump(mode="json")
    raw["detector"].update(
        {
            "evaluation_manifest": pin("eval.json", {}),
            "detector_decision": decision,
            "input_roster": roster,
        }
    )
    req = SuccessorMigrationRequest.model_validate(raw)
    validate_configuration4_binding(req.detector, evidence_root=tmp_path)
    final = json.dumps(proposal()).encode()
    artifact = capture_successor_final(
        req,
        final,
        task_id="task",
        session_id="session",
        started_at="2026-10-06T00:00:00Z",
        completed_at="2026-10-06T01:00:00Z",
        host_events=pin("events.json", {}),
        raw_transcript=pin("transcript.json", {}),
    )
    replay_successor_capture(req, artifact, exact_final=final, evidence_root=tmp_path)
    with pytest.raises(ValueError, match="exact final"):
        replay_successor_capture(
            req, artifact, exact_final=b"{}", evidence_root=tmp_path
        )
    (tmp_path / "decision.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        validate_configuration4_binding(req.detector, evidence_root=tmp_path)
