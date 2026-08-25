"""Seal one coordinator-observed configuration-3 collaboration final.

The collaboration API exposes the exact final message and task identity but
does not expose token counters or per-task timing. This handoff therefore
records those fields as unavailable instead of inventing zero values.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from cobol_archaeologist.eval.codex_batch import (
    CodexBaselineEnvelope,
    CodexBatchEnvelope,
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
from cobol_archaeologist.eval.collaboration_staging import (
    CollaborationStagingManifest,
    load_staged_tool_logs,
)
from cobol_archaeologist.eval.config3_live import CodexAdaptiveEnvelope


def _response_model(system_id: str):
    if system_id == "agent":
        return CodexBatchEnvelope
    if system_id == "adaptive_agent":
        return CodexAdaptiveEnvelope
    if system_id in {"plain_llm", "rag_dense", "rag_reranker", "oracle_slice"}:
        return CodexBaselineEnvelope
    raise ValueError(f"unsupported configuration-3 system: {system_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()

    request = CollaborationSubagentRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    final_json = args.final.read_text(encoding="utf-8").rstrip("\r\n")
    final_sha256 = hashlib.sha256(final_json.encode("utf-8")).hexdigest()
    tool_logs = ()
    if args.system in {"agent", "adaptive_agent"}:
        staging_base = args.artifact_dir / "task-staging-v1"
        manifest_path = staging_base / request.run_key / "staging-manifest.json"
        manifest = CollaborationStagingManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        tool_logs = load_staged_tool_logs(
            staging_base=staging_base,
            run_key=request.run_key,
            expected_staging_sha256=manifest.staging_sha256,
        )
    events = [
        CollaborationTranscriptEvent(
            sequence=1,
            type="task.started",
            task_name=args.task_name,
            payload=collaboration_start_receipt_payload(
                task_id=args.task_id,
                request_sha256=request.request_sha256,
            ),
        )
    ]
    events.extend(
        CollaborationTranscriptEvent(
            sequence=sequence,
            type="tool.completed",
            task_name=args.task_name,
            payload=collaboration_tool_receipt_payload(
                task_id=args.task_id,
                request_sha256=request.request_sha256,
                log=log,
            ),
        )
        for sequence, log in enumerate(tool_logs, start=2)
    )
    events.append(
        CollaborationTranscriptEvent(
            sequence=len(events) + 1,
            type="task.completed",
            task_name=args.task_name,
            payload=collaboration_completion_receipt_payload(
                task_id=args.task_id,
                request_sha256=request.request_sha256,
                final_sha256=final_sha256,
            ),
        )
    )
    submission = CollaborationSubagentSubmissionV2(
        request_sha256=request.request_sha256,
        task_name=args.task_name,
        task_id=args.task_id,
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
        tool_logs=tool_logs,
        events=tuple(events),
    )
    execution = seal_collaboration_subagent_output(
        request=request,
        submission=submission,
        response_model=_response_model(args.system),
        artifact_dir=args.artifact_dir,
        key=request.run_key,
    )
    print(execution.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
