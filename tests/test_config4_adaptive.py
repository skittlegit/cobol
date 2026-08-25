from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cobol_archaeologist.eval.codex_tool import ToolRequest
from cobol_archaeologist.eval.collaboration_staging import (
    execute_staged_tool_request,
)
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationSubagentRequest,
    CollaborationSubagentSubmissionV2,
    CollaborationTranscriptEvent,
    collaboration_completion_receipt_payload,
    collaboration_start_receipt_payload,
    collaboration_tool_receipt_payload,
    seal_collaboration_subagent_output,
)
from cobol_archaeologist.eval.config3_live import CodexAdaptiveEnvelope
from cobol_archaeologist.eval.config4_adaptive import (
    PROGRESS_NAME,
    READINESS_NAME,
    Config4ReplayFailure,
    replay_config4_adaptive_dev,
    score_config4_adaptive_readiness,
)
from cobol_archaeologist.eval.config4_prepare import (
    REQUEST_DIRECTORY_NAME,
    STAGING_DIRECTORY_NAME,
    Config4DevPreparation,
    prepare_config4_adaptive_dev,
)
from cobol_archaeologist.eval.materialize import MaterializedSource
from cobol_archaeologist.schemas import (
    CodeLocus,
    DriftInstance,
    Labels,
    Provenance,
    RegulationClause,
    SourceLocus,
)


def _row(instance_id: str, *, program: str = "CASE.cbl") -> DriftInstance:
    return DriftInstance(
        instance_id=instance_id,
        regulation_clause=RegulationClause(
            doc="Test regulation",
            clause_id="1",
            version="2026-01-01",
            effective_date="2026-01-01",
            text="The check must be present.",
            current_value=None,
        ),
        code_locus=CodeLocus(
            loci=(
                SourceLocus(
                    program=Path(program).stem,
                    paragraph="1000-MAIN",
                    file=None,
                    line_span=(1, 2),
                ),
            ),
            slice_vars=(),
            is_interprocedural=False,
        ),
        drift_type="D7_conformant",
        target_path=None,
        labels=Labels(
            program_level="conformant",
            paragraph_level="conformant",
            line_level=[],
        ),
        gold_rationale="fixture only",
        provenance=Provenance(
            source="real_curated",
            base_program=program,
            mutation=None,
            annotator_notes=None,
        ),
    )


def _write_split(root: Path, split: str, rows: list[DriftInstance]) -> None:
    path = root / "data/benchmark/v1" / f"{split}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8"
    )


def _fake_materialize(
    row: DriftInstance, *, programs_root: Path | None = None
) -> MaterializedSource:
    del programs_root
    content = (
        f"       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {Path(row.provenance.base_program).stem}.\n"
        "       PROCEDURE DIVISION.\n"
        "           STOP RUN.\n"
    )
    name = Path(row.provenance.base_program).name
    return MaterializedSource(
        main_file=name,
        files={name: content},
        source_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Config4DevPreparation]:
    _write_split(
        tmp_path,
        "dev",
        [_row("drift_100001"), _row("drift_100002", program="OTHER.cbl")],
    )
    _write_split(tmp_path, "train", [_row("drift_100003", program="TRAIN.cbl")])
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_prepare.materialize", _fake_materialize
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_prepare.runtime_source_sha256",
        lambda _root: "a" * 64,
    )
    output = tmp_path / "data/eval/m4-config4/lineage-v2/train-dev/adaptive_agent"
    preparation = prepare_config4_adaptive_dev(
        root=tmp_path,
        output_dir=output,
        selection="dev",
        limit=None,
    )
    return output, preparation


class _FakeTools:
    def grep(self, *, pattern: str) -> str:
        return f"CASE.cbl:1: {pattern}"


def _capture_abstention(output: Path, pin) -> None:
    request = CollaborationSubagentRequest.model_validate_json(
        (output / REQUEST_DIRECTORY_NAME / f"{pin.run_key}.json").read_text(
            encoding="utf-8"
        )
    )
    log_record = execute_staged_tool_request(
        ToolRequest(
            alias="drift_900000",
            hunt="adaptive",
            tool="grep",
            arguments={"pattern": "STOP RUN"},
        ),
        staging_base=output / STAGING_DIRECTORY_NAME,
        run_key=pin.run_key,
        expected_staging_sha256=pin.staging_sha256,
        tool_factory=lambda _source: _FakeTools(),
    )
    log = log_record.entry
    final_json = json.dumps(
        {
            "results": [
                {
                    "alias": "drift_900000",
                    "evidence_ledger": [
                        {
                            "observation_step": 1,
                            "observation_sha256": hashlib.sha256(
                                log.observation_summary.encode("utf-8")
                            ).hexdigest(),
                            "hypothesis": "D7_conformant",
                            "bearing": "context",
                            "rationale": "Fixture observation is retained for replay.",
                        }
                    ],
                    "response": {
                        "kind": "abstain",
                        "thought": "Fixture capture has insufficient evidence.",
                        "prediction": None,
                        "claim": None,
                        "exec_probe": None,
                        "static_claim": None,
                        "abstention_reason": "fixture abstention",
                        "final_answer": "Abstained: fixture abstention",
                    },
                }
            ]
        },
        separators=(",", ":"),
    )
    task_name = f"/config4/adaptive/{pin.run_key}"
    task_id = f"task-{pin.run_key[:12]}"
    final_sha256 = hashlib.sha256(final_json.encode("utf-8")).hexdigest()
    submission = CollaborationSubagentSubmissionV2(
        request_sha256=request.request_sha256,
        task_name=task_name,
        task_id=task_id,
        group=request.group,
        final_json=final_json,
        final_sha256=final_sha256,
        usage_evidence={
            "status": "unavailable",
            "value": "not_recorded",
            "reason": "in_product_orchestration_does_not_expose_token_usage",
        },
        timing_evidence={
            "status": "unavailable",
            "value": "not_recorded",
            "reason": "in_product_orchestration_does_not_expose_task_timing",
        },
        tool_logs=(log,),
        events=(
            CollaborationTranscriptEvent(
                sequence=1,
                type="task.started",
                task_name=task_name,
                payload=collaboration_start_receipt_payload(
                    task_id=task_id, request_sha256=request.request_sha256
                ),
            ),
            CollaborationTranscriptEvent(
                sequence=2,
                type="tool.completed",
                task_name=task_name,
                payload=collaboration_tool_receipt_payload(
                    task_id=task_id, request_sha256=request.request_sha256, log=log
                ),
            ),
            CollaborationTranscriptEvent(
                sequence=3,
                type="task.completed",
                task_name=task_name,
                payload=collaboration_completion_receipt_payload(
                    task_id=task_id,
                    request_sha256=request.request_sha256,
                    final_sha256=final_sha256,
                ),
            ),
        ),
    )
    seal_collaboration_subagent_output(
        request=request,
        submission=submission,
        response_model=CodexAdaptiveEnvelope,
        artifact_dir=output,
        key=pin.run_key,
    )


def test_replay_is_provider_free_and_distinguishes_pending_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, preparation = _prepare(tmp_path, monkeypatch)
    # A malformed sentinel proves the replay reads only the dev split.
    (tmp_path / "data/benchmark/v1/test.jsonl").write_text(
        "this is not a benchmark row\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_adaptive.materialize", _fake_materialize
    )

    readiness = replay_config4_adaptive_dev(
        root=tmp_path, output_dir=output, expected_row_count=2
    )

    assert readiness.status == "IN_PROGRESS"
    assert readiness.completed_rows == 0
    assert readiness.pending_instance_ids == (
        "drift_100001",
        "drift_100002",
    )
    assert readiness.infrastructure_failures == {}
    assert readiness.contract_rejections == {}
    assert readiness.gates["complete_102_row_dev_trial"] is False
    assert (output / PROGRESS_NAME).is_file()
    assert (output / READINESS_NAME).is_file()
    assert len(preparation.request_order) == 2


def test_replay_marks_host_artifact_failure_separately_from_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, preparation = _prepare(tmp_path, monkeypatch)
    pin = preparation.request_order[0]
    request_path = output / REQUEST_DIRECTORY_NAME / f"{pin.run_key}.json"
    request_path.write_text(
        request_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    readiness = replay_config4_adaptive_dev(
        root=tmp_path, output_dir=output, expected_row_count=2
    )

    assert readiness.status == "NOT_EVALUABLE"
    assert readiness.pending_instance_ids == ("drift_100002",)
    assert any(
        failure.instance_id == "drift_100001"
        for failure in readiness.infrastructure_failures.values()
    )
    assert readiness.contract_rejections == {}


def test_sealed_replay_record_is_resumable_and_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, preparation = _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_adaptive.materialize", _fake_materialize
    )
    _capture_abstention(output, preparation.request_order[0])

    first = replay_config4_adaptive_dev(
        root=tmp_path, output_dir=output, expected_row_count=2
    )
    record_dir = output / "adaptive-dev-records-v1"
    record_bytes = {
        path.name: path.read_bytes() for path in record_dir.iterdir()
    }
    assert first.completed_rows == 1
    assert first.pending_instance_ids == ("drift_100002",)

    def replay_must_not_run(*args, **kwargs):
        raise AssertionError("an immutable completed run key was replayed")

    monkeypatch.setattr(
        "cobol_archaeologist.eval.config4_adaptive._replay_adaptive_record",
        replay_must_not_run,
    )
    second = replay_config4_adaptive_dev(
        root=tmp_path, output_dir=output, expected_row_count=2
    )

    assert second.completed_rows == 1
    assert second.pending_instance_ids == ("drift_100002",)
    assert {
        path.name: path.read_bytes() for path in record_dir.iterdir()
    } == record_bytes


def test_readiness_gates_preserve_pending_and_failure_states() -> None:
    pending = score_config4_adaptive_readiness(
        records=(),
        expected_row_count=102,
        freeze_sha256="a" * 64,
        pending_instance_ids=("drift_100001",),
    )
    assert pending.status == "IN_PROGRESS"
    assert pending.infrastructure_failures == {}
    assert pending.contract_rejections == {}

    failure = Config4ReplayFailure(
        kind="infrastructure",
        instance_id="drift_100002",
        reason="fixture host failure",
    )
    not_evaluable = score_config4_adaptive_readiness(
        records=(),
        expected_row_count=102,
        freeze_sha256="a" * 64,
        pending_instance_ids=("drift_100001",),
        infrastructure_failures={"drift_100002:host": failure},
    )
    assert not_evaluable.status == "NOT_EVALUABLE"
    assert not_evaluable.pending_instance_ids == ("drift_100001",)
    assert not_evaluable.infrastructure_failures["drift_100002:host"] == failure
    assert not_evaluable.gates["zero_infrastructure_failures"] is False
