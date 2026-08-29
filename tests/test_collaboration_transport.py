from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from cobol_archaeologist.eval.codex_batch import ParsedCodexEvents
from cobol_archaeologist.eval.codex_live import batch_size_for
from cobol_archaeologist.eval.codex_tool import ToolLogEntry
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationBundleMarker,
    CollaborationGroupIdentity,
    CollaborationSubagentExecution,
    CollaborationSubagentExecutionV2,
    CollaborationSubagentRequest,
    CollaborationSubagentSubmission,
    CollaborationSubagentSubmissionV2,
    CollaborationTranscriptEvent,
    build_collaboration_request,
    collaboration_completion_receipt_payload,
    collaboration_start_receipt_payload,
    collaboration_tool_receipt_payload,
    ensure_collaboration_request,
    load_collaboration_bundle,
    seal_collaboration_subagent_output,
    self_contained_collaboration_prompt,
)
from cobol_archaeologist.eval.config3_live import (
    ADAPTIVE_BATCH_SIZE,
    CONFIG3_SYSTEMS,
    CodexAdaptiveEnvelope,
    Config3RunFreeze,
)
from cobol_archaeologist.eval.materialize import MaterializedSource

ROOT = Path(__file__).resolve().parents[1]


class _Response(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


def _request(*, authorized_hunts=()):
    source = MaterializedSource(
        main_file="CASE.cbl", files={"CASE.cbl": "STOP RUN.\n"}, source_sha256="a" * 64
    )
    return build_collaboration_request(
        run_key="b" * 64,
        prompt="Judge exactly one opaque case.",
        schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        sources={"drift_900000": source},
        runtime_source_sha256="c" * 64,
        authorized_hunts=authorized_hunts,
        visible_cases=1,
        group=CollaborationGroupIdentity(
            group_id="smoke/plain_llm/group-01",
            mode="concurrent",
            ordinal=1,
            size=3,
        ),
    )


def _submission(request):
    final = '{"answer":"D7_conformant"}'
    task = "/root/config3/plain_llm_01"
    task_id = "task-01"
    return CollaborationSubagentSubmissionV2(
        request_sha256=request.request_sha256,
        task_name=task,
        task_id=task_id,
        group=request.group,
        final_json=final,
        final_sha256=hashlib.sha256(final.encode()).hexdigest(),
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
        tool_logs=(),
        events=(
            CollaborationTranscriptEvent(
                sequence=1,
                type="task.started",
                task_name=task,
                payload={
                    "task_id": task_id,
                    "request_sha256": request.request_sha256,
                },
            ),
            CollaborationTranscriptEvent(
                sequence=2,
                type="task.completed",
                task_name=task,
                payload={
                    "task_id": task_id,
                    "request_sha256": request.request_sha256,
                    "final_sha256": hashlib.sha256(final.encode()).hexdigest(),
                    "status": "completed",
                },
            ),
        ),
    )


def _adaptive_log(*, error: str | None = None) -> ToolLogEntry:
    return ToolLogEntry(
        alias="drift_900000",
        hunt="adaptive",
        sequence=1,
        tool="grep",
        arguments={"pattern": "STOP RUN"},
        observation_summary=(
            "tool failed" if error is not None else "CASE.cbl:1: STOP RUN."
        ),
        observation_truncated=False,
        error=error,
        latency_ms=1.0,
    )


def _submission_with_logs(
    request,
    logs: tuple[ToolLogEntry, ...],
    *,
    final_json: str | None = None,
):
    base = _submission(request)
    final_json = final_json or base.final_json
    final_sha256 = hashlib.sha256(final_json.encode()).hexdigest()
    raw = base.model_dump(mode="json")
    raw["final_json"] = final_json
    raw["final_sha256"] = final_sha256
    raw["tool_logs"] = [log.model_dump(mode="json") for log in logs]
    raw["events"] = [
        {
            "sequence": 1,
            "type": "task.started",
            "task_name": base.task_name,
            "payload": collaboration_start_receipt_payload(
                task_id=base.task_id,
                request_sha256=request.request_sha256,
            ),
        },
        *(
            {
                "sequence": sequence,
                "type": "tool.completed",
                "task_name": base.task_name,
                "payload": collaboration_tool_receipt_payload(
                    task_id=base.task_id,
                    request_sha256=request.request_sha256,
                    log=log,
                ),
            }
            for sequence, log in enumerate(logs, start=2)
        ),
        {
            "sequence": len(logs) + 2,
            "type": "task.completed",
            "task_name": base.task_name,
            "payload": collaboration_completion_receipt_payload(
                task_id=base.task_id,
                request_sha256=request.request_sha256,
                final_sha256=final_sha256,
            ),
        },
    ]
    return CollaborationSubagentSubmissionV2.model_validate(raw)


def _legacy_submission(request):
    final = '{"answer":"D7_conformant"}'
    task = "/root/config3/plain_llm_legacy"
    task_id = "legacy-task-01"
    return CollaborationSubagentSubmission(
        request_sha256=request.request_sha256,
        task_name=task,
        task_id=task_id,
        group=request.group,
        final_json=final,
        final_sha256=hashlib.sha256(final.encode()).hexdigest(),
        usage={"input_tokens": 10, "output_tokens": 4},
        tool_logs=(),
        events=(
            CollaborationTranscriptEvent(
                sequence=1,
                type="task.started",
                task_name=task,
                payload={"task_id": task_id},
            ),
            CollaborationTranscriptEvent(
                sequence=2,
                type="task.completed",
                task_name=task,
                payload={
                    "task_id": task_id,
                    "final_sha256": hashlib.sha256(final.encode()).hexdigest(),
                },
            ),
        ),
    )


def _canonical_hash(value) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def test_collaboration_output_is_typed_sealed_and_resumable(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "requests" / "one.json"
    ensure_collaboration_request(request_path, request)
    ensure_collaboration_request(request_path, request)

    execution = seal_collaboration_subagent_output(
        request=request,
        submission=_submission(request),
        response_model=_Response,
        artifact_dir=tmp_path,
        key=request.run_key,
    )
    replay = load_collaboration_bundle(
        artifact_dir=tmp_path,
        key=request.run_key,
        expected_request_sha256=request.request_sha256,
    )

    assert isinstance(execution, CollaborationSubagentExecutionV2)
    assert replay == execution
    assert execution.transport == "collaboration_subagent"
    assert execution.provider == "collaboration_subagent"
    assert (
        execution.request.schema_version == "configuration-3-collaboration-request-v2"
    )
    assert execution.request.prompt.startswith("Judge exactly one opaque case.\n\n")
    assert execution.request.prompt.endswith(
        '{"additionalProperties":false,"properties":{"answer":{"type":"string"}},'
        '"required":["answer"],"type":"object"}'
    )
    assert execution.final_message == '{"answer":"D7_conformant"}'
    assert execution.group.mode == "concurrent"
    assert execution.parsed.usage is None
    assert execution.evidence_scope == "descriptive_correctness_only"
    assert execution.resource_evidence_valid is False


def test_adaptive_capture_rejects_zero_staged_observations(tmp_path: Path) -> None:
    request = _request(authorized_hunts=("adaptive",))

    with pytest.raises(ValueError, match="successful staged observation"):
        seal_collaboration_subagent_output(
            request=request,
            submission=_submission(request),
            response_model=_Response,
            artifact_dir=tmp_path,
            key=request.run_key,
        )

    assert not (tmp_path / "raw" / request.run_key / "complete").exists()


def test_adaptive_capture_rejects_all_error_staged_observations(tmp_path: Path) -> None:
    request = _request(authorized_hunts=("adaptive",))
    submission = _submission_with_logs(request, (_adaptive_log(error="tool failed"),))

    with pytest.raises(ValueError, match="successful staged observation"):
        seal_collaboration_subagent_output(
            request=request,
            submission=submission,
            response_model=_Response,
            artifact_dir=tmp_path,
            key=request.run_key,
        )

    assert not (tmp_path / "raw" / request.run_key / "complete").exists()


def test_adaptive_capture_accepts_explicit_abstention_after_successful_observation(
    tmp_path: Path,
) -> None:
    request = _request(authorized_hunts=("adaptive",))
    final_json = json.dumps(
        {
            "results": [
                {
                    "alias": "drift_900000",
                    "evidence_ledger": [],
                    "response": {
                        "kind": "abstain",
                        "thought": "The evidence is insufficient.",
                        "prediction": None,
                        "claim": None,
                        "exec_probe": None,
                        "static_claim": None,
                        "abstention_reason": "insufficient evidence",
                        "final_answer": "Abstained: insufficient evidence",
                    },
                }
            ]
        },
        separators=(",", ":"),
    )
    execution = seal_collaboration_subagent_output(
        request=request,
        submission=_submission_with_logs(
            request, (_adaptive_log(),), final_json=final_json
        ),
        response_model=CodexAdaptiveEnvelope,
        artifact_dir=tmp_path,
        key=request.run_key,
    )

    assert len(execution.tool_logs) == 1
    assert execution.tool_logs[0].error is None
    assert execution.final_message == final_json
    assert (tmp_path / "raw" / request.run_key / "complete").is_file()


def test_baseline_no_tool_capture_remains_allowed(tmp_path: Path) -> None:
    request = _request()
    execution = seal_collaboration_subagent_output(
        request=request,
        submission=_submission(request),
        response_model=_Response,
        artifact_dir=tmp_path,
        key=request.run_key,
    )

    assert execution.tool_logs == []
    assert (tmp_path / "raw" / request.run_key / "complete").is_file()


def test_unavailable_usage_is_not_zero_filled_or_resource_valid(tmp_path: Path) -> None:
    request = _request()
    submission = _submission(request)
    execution = seal_collaboration_subagent_output(
        request=request,
        submission=submission,
        response_model=_Response,
        artifact_dir=tmp_path,
        key=request.run_key,
    )

    assert execution.usage_evidence.status == "unavailable"
    assert execution.usage_evidence.value == "not_recorded"
    assert execution.parsed.usage is None
    assert "input_tokens" not in execution.usage_evidence.model_dump()

    raw = submission.model_dump(mode="json")
    raw["usage_evidence"]["input_tokens"] = 0
    with pytest.raises(ValidationError, match="input_tokens"):
        CollaborationSubagentSubmissionV2.model_validate(raw)

    raw = submission.model_dump(mode="json")
    raw["usage_evidence"] = {
        "status": "reported",
        "source": "orchestrator_runtime",
    }
    with pytest.raises(ValidationError, match="input_tokens"):
        CollaborationSubagentSubmissionV2.model_validate(raw)


def test_runtime_reported_usage_and_timing_are_exactly_resource_valid(
    tmp_path: Path,
) -> None:
    request = _request()
    raw = _submission(request).model_dump(mode="json")
    raw["usage_evidence"] = {
        "status": "reported",
        "source": "orchestrator_runtime",
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "output_tokens": 4,
    }
    raw["timing_evidence"] = {
        "status": "reported",
        "source": "coordinator_monotonic",
        "elapsed_ms": 25.5,
    }
    submission = CollaborationSubagentSubmissionV2.model_validate(raw)
    execution = seal_collaboration_subagent_output(
        request=request,
        submission=submission,
        response_model=_Response,
        artifact_dir=tmp_path,
        key=request.run_key,
    )

    assert execution.parsed.usage is not None
    assert execution.parsed.usage.input_tokens == 10
    assert execution.parsed.usage.cached_input_tokens == 2
    assert execution.parsed.usage.output_tokens == 4
    assert execution.evidence_scope == "correctness_and_resources"
    assert execution.resource_evidence_valid is True


def test_v2_receipts_bind_start_and_completion_task_identity() -> None:
    request = _request()
    raw = _submission(request).model_dump(mode="json")
    raw["events"][0]["payload"]["task_id"] = "different-task"
    with pytest.raises(ValueError, match="start receipt"):
        CollaborationSubagentSubmissionV2.model_validate(raw)

    raw = _submission(request).model_dump(mode="json")
    raw["events"][-1]["payload"]["status"] = "errored"
    with pytest.raises(ValueError, match="completion receipt"):
        CollaborationSubagentSubmissionV2.model_validate(raw)


def test_v2_tool_event_binds_exact_tool_log_hash() -> None:
    request = _request(authorized_hunts=("D7_conformant",))
    base = _submission(request)
    log = ToolLogEntry(
        alias="drift_900000",
        hunt="D7_conformant",
        sequence=1,
        tool="grep",
        arguments={"pattern": "STOP RUN"},
        observation_summary="CASE.cbl:1: STOP RUN.",
        observation_truncated=False,
        error=None,
        latency_ms=1.0,
    )
    raw = base.model_dump(mode="json")
    raw["tool_logs"] = [log.model_dump(mode="json")]
    raw["events"].insert(
        1,
        {
            "sequence": 2,
            "type": "tool.completed",
            "task_name": base.task_name,
            "payload": collaboration_tool_receipt_payload(
                task_id=base.task_id,
                request_sha256=request.request_sha256,
                log=log,
            ),
        },
    )
    raw["events"][-1]["sequence"] = 3
    assert CollaborationSubagentSubmissionV2.model_validate(raw).tool_logs == (log,)

    raw["events"][1]["payload"]["tool_log_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="exact tool log"):
        CollaborationSubagentSubmissionV2.model_validate(raw)


def test_request_v2_requires_exact_schema_in_one_model_visible_prompt() -> None:
    request = _request()
    assert request.prompt == self_contained_collaboration_prompt(
        "Judge exactly one opaque case.", request.response_schema
    )

    raw = request.model_dump(mode="json")
    raw["prompt"] = "Judge exactly one opaque case."
    raw["prompt_sha256"] = hashlib.sha256(raw["prompt"].encode()).hexdigest()
    with pytest.raises(ValueError, match="omits its exact response schema"):
        CollaborationSubagentRequest.model_validate(raw)


def test_legacy_request_v1_remains_loadable_as_preserved_diagnostic() -> None:
    request = _request()
    prompt = "Judge exactly one opaque case."
    raw = request.model_dump(mode="json")
    raw["schema_version"] = "configuration-3-collaboration-request-v1"
    raw["prompt"] = prompt
    raw["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
    from cobol_archaeologist.eval.collaboration_transport import (
        collaboration_request_sha256,
    )

    raw["request_sha256"] = collaboration_request_sha256(
        run_key=request.run_key,
        prompt=prompt,
        schema=request.response_schema,
        source_sha256=request.source_sha256,
        runtime_source_sha256=request.runtime_source_sha256,
        authorized_hunts=request.authorized_hunts,
        visible_cases=request.visible_cases,
        group=request.group,
    )

    legacy = CollaborationSubagentRequest.model_validate(raw)
    assert legacy.schema_version == "configuration-3-collaboration-request-v1"
    assert legacy.prompt == prompt


def test_collaboration_tampering_and_relabeling_fail_closed(tmp_path: Path) -> None:
    request = _request()
    bad = _submission(request).model_copy(update={"final_json": '{"answer":"x"}'})
    with pytest.raises(ValueError, match="final JSON hash"):
        CollaborationSubagentSubmissionV2.model_validate(bad.model_dump())

    with pytest.raises(ValidationError, match="must not be labeled"):
        Config3RunFreeze.model_validate(
            {
                "provider": "chatgpt-codex",
                "authentication": "ChatGPT",
                "transport": "collaboration_subagent",
                "prompt_version": "v1",
                "repository_commit": "a" * 40,
                "runtime_source_sha256": "b" * 64,
                "max_workers": 3,
                "systems": ["adaptive_agent"],
                "budgets": {},
                "batch_sizes": {},
                "identity_hashes": {},
                "phase5_baseline_sha256": {},
                "phase5_aggregate_sha256": {},
                "dev_split_path": "dev",
                "dev_split_sha256": "c" * 64,
                "train_split_path": "train",
                "train_split_sha256": "d" * 64,
                "test_split_path": "test",
                "test_split_sha256": "e" * 64,
                "t6_v2_path": "t6",
                "t6_v2_sha256": "f" * 64,
                "smoke_seed": 1,
                "smoke_instance_ids": [f"d-{i}" for i in range(14)],
                "dev_order": [],
                "test_order": [],
                "t6_order": [],
                "t6_source_inputs": {},
                "source_sha256": {},
            }
        )


def test_submission_v1_is_load_only_and_legacy_bundle_still_loads(
    tmp_path: Path,
) -> None:
    request = _request()
    submission = _legacy_submission(request)
    with pytest.raises(TypeError, match="submission-v1 is load-only"):
        seal_collaboration_subagent_output(
            request=request,
            submission=submission,
            response_model=_Response,
            artifact_dir=tmp_path,
            key=request.run_key,
        )

    event_payload = [event.model_dump(mode="json") for event in submission.events]
    execution = CollaborationSubagentExecution(
        request=request,
        task_name=submission.task_name,
        task_id=submission.task_id,
        group=submission.group,
        parsed=ParsedCodexEvents(
            final_message=submission.final_json,
            usage=submission.usage,
            thread_id=submission.task_id,
            events=event_payload,
        ),
        final_message=submission.final_json,
        tool_logs=[],
        request_sha256=request.request_sha256,
        event_stream_sha256=_canonical_hash(event_payload),
        tool_logs_sha256=_canonical_hash([]),
        transcript_sha256=_canonical_hash(
            {
                "task_name": submission.task_name,
                "task_id": submission.task_id,
                "prompt": request.prompt,
                "final_json": submission.final_json,
                "events": event_payload,
            }
        ),
    )
    marker = CollaborationBundleMarker(
        key=request.run_key,
        request_sha256=request.request_sha256,
        request_artifact_sha256=_canonical_hash(request),
        execution_sha256=_canonical_hash(execution),
        event_stream_sha256=execution.event_stream_sha256,
        tool_logs_sha256=execution.tool_logs_sha256,
        transcript_sha256=execution.transcript_sha256,
    )
    raw_dir = tmp_path / "raw" / request.run_key
    raw_dir.mkdir(parents=True)
    (raw_dir / "request.json").write_text(
        request.model_dump_json(indent=2), encoding="utf-8"
    )
    (raw_dir / "execution.json").write_text(
        execution.model_dump_json(indent=2), encoding="utf-8"
    )
    (raw_dir / "complete").write_text(
        marker.model_dump_json(indent=2), encoding="utf-8"
    )

    assert (
        load_collaboration_bundle(
            artifact_dir=tmp_path,
            key=request.run_key,
            expected_request_sha256=request.request_sha256,
        )
        == execution
    )


def test_sealed_bundle_rejects_post_completion_mutation(tmp_path: Path) -> None:
    request = _request()
    seal_collaboration_subagent_output(
        request=request,
        submission=_submission(request),
        response_model=_Response,
        artifact_dir=tmp_path,
        key=request.run_key,
    )
    execution_path = tmp_path / "raw" / request.run_key / "execution.json"
    payload = json.loads(execution_path.read_text(encoding="utf-8"))
    payload["task_id"] = "tampered"
    execution_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        load_collaboration_bundle(artifact_dir=tmp_path, key=request.run_key)


def test_partial_collaboration_bundle_resumes_only_with_identical_bytes(
    tmp_path: Path,
) -> None:
    request = _request()
    submission = _submission(request)
    raw = tmp_path / "raw" / request.run_key
    raw.mkdir(parents=True)
    (raw / "request.json").write_text(
        request.model_dump_json(indent=2), encoding="utf-8"
    )

    execution = seal_collaboration_subagent_output(
        request=request,
        submission=submission,
        response_model=_Response,
        artifact_dir=tmp_path,
        key=request.run_key,
    )
    assert (
        load_collaboration_bundle(
            artifact_dir=tmp_path,
            key=request.run_key,
            expected_request_sha256=request.request_sha256,
        )
        == execution
    )

    bad_root = tmp_path / "bad"
    bad_raw = bad_root / "raw" / request.run_key
    bad_raw.mkdir(parents=True)
    (bad_raw / "request.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="partial collaboration artifact"):
        seal_collaboration_subagent_output(
            request=request,
            submission=submission,
            response_model=_Response,
            artifact_dir=bad_root,
            key=request.run_key,
        )


def test_collaboration_smoke_plan_matches_frozen_roster_and_batching() -> None:
    plan = json.loads(
        (
            ROOT / "data/eval/legacy/m4-config3/collaboration-smoke-plan.json"
        ).read_text(
            encoding="utf-8"
        )
    )
    roster_path = ROOT / "data/eval/legacy/m4-config3/development-smoke.json"
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    expected_batches = {
        system_id: (
            ADAPTIVE_BATCH_SIZE
            if system_id == "adaptive_agent"
            else batch_size_for(system_id)
        )
        for system_id in CONFIG3_SYSTEMS
    }
    systems = {row["system_id"]: row for row in plan["systems"]}

    assert plan["status"] == "REQUEST_IDENTITIES_PENDING_RUN_FREEZE"
    assert plan["transport"] == "collaboration_subagent"
    assert plan["provider"] == "collaboration_subagent"
    assert plan["authentication"] == "in_product_orchestration"
    assert plan["model_id"] == "gpt-5.6-luna"
    assert plan["reasoning_effort"] == "max"
    assert (
        plan["development_smoke_sha256"]
        == hashlib.sha256(roster_path.read_bytes()).hexdigest()
    )
    assert plan["row_count"] == len(roster["rows"]) == 14
    assert plan["hidden_test_rows"] == roster["hidden_test_rows"] == 0
    assert tuple(systems) == CONFIG3_SYSTEMS
    assert {key: value["batch_size"] for key, value in systems.items()} == (
        expected_batches
    )
    assert all(
        systems[system_id]["task_count"]
        == math.ceil(plan["row_count"] / expected_batches[system_id])
        for system_id in CONFIG3_SYSTEMS
    )
    assert plan["system_row_evaluations"] == plan["row_count"] * len(systems)
    assert plan["task_count"] == sum(row["task_count"] for row in systems.values())
