"""Typed, immutable ingestion for in-product configuration-3 subagent tasks.

This transport never impersonates the legacy Codex CLI.  A coordinator freezes
one exact request, an external in-product orchestrator runs the isolated task,
and this module validates and seals the returned task transcript for host replay.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.eval.codex_batch import CodexUsage, ParsedCodexEvents
from cobol_archaeologist.eval.codex_tool import ADAPTIVE_HUNT, ToolLogEntry
from cobol_archaeologist.eval.materialize import MaterializedSource

MODEL_ID = "gpt-5.6-luna"
REASONING_EFFORT = "max"
TRANSPORT_ID = "collaboration_subagent"
PROVIDER_ID = "collaboration_subagent"
AUTHENTICATION = "in_product_orchestration"
REQUEST_SCHEMA_V1 = "configuration-3-collaboration-request-v1"
REQUEST_SCHEMA_V2 = "configuration-3-collaboration-request-v2"
REQUEST_DIRECTORY_V2 = "requests-v2"
_RESPONSE_CONTRACT_HEADER = (
    "STRICT RESPONSE CONTRACT (part of this frozen model-visible prompt):\n"
    "Return exactly one JSON object matching the JSON Schema below. "
    "Do not wrap it in Markdown and do not include any text before or after it.\n"
    "JSON Schema (canonical JSON):\n"
)


def _canonical_bytes(value: BaseModel | Mapping[str, Any] | list[Any]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def collaboration_tool_log_sha256(log: ToolLogEntry) -> str:
    """Hash one exact staged log entry for its coordinator tool receipt."""

    return _sha_bytes(_canonical_bytes(log))


def collaboration_start_receipt_payload(
    *, task_id: str, request_sha256: str
) -> dict[str, Any]:
    return {"task_id": task_id, "request_sha256": request_sha256}


def collaboration_tool_receipt_payload(
    *, task_id: str, request_sha256: str, log: ToolLogEntry
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "request_sha256": request_sha256,
        "tool_log_sequence": log.sequence,
        "tool_log_sha256": collaboration_tool_log_sha256(log),
    }


def collaboration_completion_receipt_payload(
    *, task_id: str, request_sha256: str, final_sha256: str
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "request_sha256": request_sha256,
        "final_sha256": final_sha256,
        "status": "completed",
    }


def self_contained_collaboration_prompt(prompt: str, schema: Mapping[str, Any]) -> str:
    """Append the exact response contract for one-message subagent transports."""

    canonical_schema = _canonical_bytes(dict(schema)).decode("utf-8")
    return f"{prompt}\n\n{_RESPONSE_CONTRACT_HEADER}{canonical_schema}"


class CollaborationGroupIdentity(BaseModel):
    """Stable sequential/concurrent placement within one frozen coordinator group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str = Field(min_length=1)
    mode: Literal["sequential", "concurrent"]
    ordinal: int = Field(ge=1)
    size: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordinal_is_in_group(self) -> CollaborationGroupIdentity:
        if self.ordinal > self.size:
            raise ValueError("collaboration group ordinal exceeds group size")
        return self


class CollaborationSubagentRequest(BaseModel):
    """Exact model-visible request frozen before external orchestration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[
        "configuration-3-collaboration-request-v1",
        "configuration-3-collaboration-request-v2",
    ] = REQUEST_SCHEMA_V2
    transport: Literal["collaboration_subagent"] = TRANSPORT_ID
    provider: Literal["collaboration_subagent"] = PROVIDER_ID
    authentication: Literal["in_product_orchestration"] = AUTHENTICATION
    model_id: Literal["gpt-5.6-luna"] = MODEL_ID
    reasoning_effort: Literal["max"] = REASONING_EFFORT
    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_schema: dict[str, Any]
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: dict[str, str]
    runtime_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_hunts: tuple[str, ...]
    visible_cases: int = Field(ge=1)
    prior_case_context_included: Literal[False] = False
    group: CollaborationGroupIdentity

    @model_validator(mode="after")
    def _hashes_match_exact_payloads(self) -> CollaborationSubagentRequest:
        if self.schema_version == REQUEST_SCHEMA_V2:
            canonical_schema = _canonical_bytes(self.response_schema).decode("utf-8")
            expected_suffix = f"\n\n{_RESPONSE_CONTRACT_HEADER}{canonical_schema}"
            if not self.prompt.endswith(expected_suffix):
                raise ValueError(
                    "collaboration request-v2 prompt omits its exact response schema"
                )
        if _sha_bytes(self.prompt.encode("utf-8")) != self.prompt_sha256:
            raise ValueError("collaboration prompt hash differs from exact text")
        if _sha_bytes(_canonical_bytes(self.response_schema)) != self.schema_sha256:
            raise ValueError("collaboration schema hash differs from exact schema")
        expected = collaboration_request_sha256(
            run_key=self.run_key,
            prompt=self.prompt,
            schema=self.response_schema,
            source_sha256=self.source_sha256,
            runtime_source_sha256=self.runtime_source_sha256,
            authorized_hunts=self.authorized_hunts,
            visible_cases=self.visible_cases,
            group=self.group,
        )
        if self.request_sha256 != expected:
            raise ValueError("collaboration request identity differs from payload")
        return self


class CollaborationTranscriptEvent(BaseModel):
    """Host-captured in-product task event; content remains exact JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    type: Literal["task.started", "tool.completed", "task.completed"]
    task_name: str = Field(min_length=1)
    payload: dict[str, Any]


class CollaborationSubagentSubmission(BaseModel):
    """Legacy v1 submission model retained only to load preserved diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-collaboration-submission-v1"] = (
        "configuration-3-collaboration-submission-v1"
    )
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    model_id: Literal["gpt-5.6-luna"] = MODEL_ID
    reasoning_effort: Literal["max"] = REASONING_EFFORT
    group: CollaborationGroupIdentity
    final_json: str = Field(min_length=2)
    final_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage: CodexUsage
    tool_logs: tuple[ToolLogEntry, ...]
    events: tuple[CollaborationTranscriptEvent, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _transcript_is_exact_and_complete(self) -> CollaborationSubagentSubmission:
        if _sha_bytes(self.final_json.encode("utf-8")) != self.final_sha256:
            raise ValueError("collaboration final JSON hash differs from exact bytes")
        if [event.sequence for event in self.events] != list(
            range(1, len(self.events) + 1)
        ):
            raise ValueError("collaboration transcript sequence is not contiguous")
        if self.events[0].type != "task.started":
            raise ValueError("collaboration transcript must start with task.started")
        if self.events[-1].type != "task.completed":
            raise ValueError("collaboration transcript must end with task.completed")
        if any(event.task_name != self.task_name for event in self.events):
            raise ValueError("collaboration transcript task name changed")
        final_payload = self.events[-1].payload
        if (
            final_payload.get("task_id") != self.task_id
            or final_payload.get("final_sha256") != self.final_sha256
        ):
            raise ValueError("collaboration completion event differs from final task")
        tool_events = sum(event.type == "tool.completed" for event in self.events)
        if tool_events != len(self.tool_logs):
            raise ValueError("collaboration tool events differ from tool logs")
        return self


class ReportedCollaborationUsage(BaseModel):
    """Exact token counters reported by the orchestration runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["reported"] = "reported"
    source: Literal["orchestrator_runtime"] = "orchestrator_runtime"
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)

    def as_codex_usage(self) -> CodexUsage:
        return CodexUsage(
            input_tokens=self.input_tokens,
            cached_input_tokens=self.cached_input_tokens,
            output_tokens=self.output_tokens,
        )


class UnavailableCollaborationUsage(BaseModel):
    """Explicit absence of provider token telemetry; never a zero counter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unavailable"] = "unavailable"
    value: Literal["not_recorded"] = "not_recorded"
    reason: Literal["in_product_orchestration_does_not_expose_token_usage"] = (
        "in_product_orchestration_does_not_expose_token_usage"
    )


CollaborationUsageEvidence = Annotated[
    ReportedCollaborationUsage | UnavailableCollaborationUsage,
    Field(discriminator="status"),
]


class ReportedCollaborationTiming(BaseModel):
    """Coordinator-observed elapsed time measured with a monotonic clock."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["reported"] = "reported"
    source: Literal["coordinator_monotonic"] = "coordinator_monotonic"
    elapsed_ms: float = Field(ge=0)


class UnavailableCollaborationTiming(BaseModel):
    """Explicit absence of provider/coordinator timing telemetry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unavailable"] = "unavailable"
    value: Literal["not_recorded"] = "not_recorded"
    reason: Literal["in_product_orchestration_does_not_expose_task_timing"] = (
        "in_product_orchestration_does_not_expose_task_timing"
    )


CollaborationTimingEvidence = Annotated[
    ReportedCollaborationTiming | UnavailableCollaborationTiming,
    Field(discriminator="status"),
]


class CollaborationSubagentSubmissionV2(BaseModel):
    """Coordinator-observed capture awaiting validation and immutable sealing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-collaboration-submission-v2"] = (
        "configuration-3-collaboration-submission-v2"
    )
    capture_source: Literal["coordinator_observed_collaboration_api"] = (
        "coordinator_observed_collaboration_api"
    )
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    model_id: Literal["gpt-5.6-luna"] = MODEL_ID
    reasoning_effort: Literal["max"] = REASONING_EFFORT
    group: CollaborationGroupIdentity
    final_json: str = Field(min_length=2)
    final_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage_evidence: CollaborationUsageEvidence
    timing_evidence: CollaborationTimingEvidence
    tool_logs: tuple[ToolLogEntry, ...]
    events: tuple[CollaborationTranscriptEvent, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _capture_is_exact_and_complete(self) -> CollaborationSubagentSubmissionV2:
        if _sha_bytes(self.final_json.encode("utf-8")) != self.final_sha256:
            raise ValueError("collaboration final JSON hash differs from exact bytes")
        if [event.sequence for event in self.events] != list(
            range(1, len(self.events) + 1)
        ):
            raise ValueError("collaboration transcript sequence is not contiguous")
        if self.events[0].type != "task.started":
            raise ValueError("collaboration transcript must start with task.started")
        if self.events[-1].type != "task.completed":
            raise ValueError("collaboration transcript must end with task.completed")
        if any(event.task_name != self.task_name for event in self.events):
            raise ValueError("collaboration transcript task name changed")
        if self.events[0].payload != collaboration_start_receipt_payload(
            task_id=self.task_id, request_sha256=self.request_sha256
        ):
            raise ValueError("collaboration start receipt differs from frozen task")
        if self.events[-1].payload != collaboration_completion_receipt_payload(
            task_id=self.task_id,
            request_sha256=self.request_sha256,
            final_sha256=self.final_sha256,
        ):
            raise ValueError("collaboration completion receipt differs from final task")
        tool_events = [event for event in self.events if event.type == "tool.completed"]
        if len(tool_events) != len(self.tool_logs):
            raise ValueError("collaboration tool events differ from tool logs")
        for event, log in zip(tool_events, self.tool_logs, strict=True):
            if event.payload != collaboration_tool_receipt_payload(
                task_id=self.task_id,
                request_sha256=self.request_sha256,
                log=log,
            ):
                raise ValueError("collaboration tool event differs from exact tool log")
        return self


class CollaborationParsedEventsV2(BaseModel):
    """Parsed capture whose provider usage may honestly be unavailable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    final_message: str
    usage: CodexUsage | None
    thread_id: str
    events: list[dict[str, Any]]


class CollaborationSubagentExecution(BaseModel):
    """Legacy v1 execution retained for immutable bundle replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transport: Literal["collaboration_subagent"] = TRANSPORT_ID
    provider: Literal["collaboration_subagent"] = PROVIDER_ID
    request: CollaborationSubagentRequest
    task_name: str
    task_id: str
    group: CollaborationGroupIdentity
    parsed: ParsedCodexEvents
    final_message: str
    tool_logs: list[ToolLogEntry]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_stream_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_logs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CollaborationSubagentExecutionV2(BaseModel):
    """Sealed v2 capture, with resource validity explicit and non-inferred."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-collaboration-execution-v2"] = (
        "configuration-3-collaboration-execution-v2"
    )
    transport: Literal["collaboration_subagent"] = TRANSPORT_ID
    provider: Literal["collaboration_subagent"] = PROVIDER_ID
    capture_source: Literal["coordinator_observed_collaboration_api"]
    request: CollaborationSubagentRequest
    task_name: str
    task_id: str
    group: CollaborationGroupIdentity
    parsed: CollaborationParsedEventsV2
    final_message: str
    usage_evidence: CollaborationUsageEvidence
    timing_evidence: CollaborationTimingEvidence
    evidence_scope: Literal["descriptive_correctness_only", "correctness_and_resources"]
    resource_evidence_valid: bool
    tool_logs: list[ToolLogEntry]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_stream_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_logs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _resource_scope_matches_telemetry(self) -> CollaborationSubagentExecutionV2:
        reported = (
            self.usage_evidence.status == "reported"
            and self.timing_evidence.status == "reported"
        )
        expected_scope = (
            "correctness_and_resources" if reported else "descriptive_correctness_only"
        )
        if (
            self.resource_evidence_valid != reported
            or self.evidence_scope != expected_scope
        ):
            raise ValueError("collaboration resource validity differs from telemetry")
        expected_usage = (
            self.usage_evidence.as_codex_usage()
            if isinstance(self.usage_evidence, ReportedCollaborationUsage)
            else None
        )
        if self.parsed.usage != expected_usage:
            raise ValueError("collaboration parsed usage differs from usage evidence")
        return self


class CollaborationBundleMarker(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-collaboration-bundle-v1"] = (
        "configuration-3-collaboration-bundle-v1"
    )
    transport: Literal["collaboration_subagent"] = TRANSPORT_ID
    key: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_stream_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_logs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CollaborationBundleMarkerV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-collaboration-bundle-v2"] = (
        "configuration-3-collaboration-bundle-v2"
    )
    transport: Literal["collaboration_subagent"] = TRANSPORT_ID
    key: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_stream_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_logs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_scope: Literal["descriptive_correctness_only", "correctness_and_resources"]
    resource_evidence_valid: bool


def collaboration_request_sha256(
    *,
    run_key: str,
    prompt: str,
    schema: Mapping[str, Any],
    source_sha256: Mapping[str, str],
    runtime_source_sha256: str,
    authorized_hunts: Sequence[str],
    visible_cases: int,
    group: CollaborationGroupIdentity,
) -> str:
    """Hash every model/method/input/group field without any OAuth identity."""

    return _sha_bytes(
        _canonical_bytes(
            {
                "transport": TRANSPORT_ID,
                "provider": PROVIDER_ID,
                "authentication": AUTHENTICATION,
                "model_id": MODEL_ID,
                "reasoning_effort": REASONING_EFFORT,
                "run_key": run_key,
                "prompt_sha256": _sha_bytes(prompt.encode("utf-8")),
                "schema_sha256": _sha_bytes(_canonical_bytes(schema)),
                "source_sha256": dict(sorted(source_sha256.items())),
                "runtime_source_sha256": runtime_source_sha256,
                "authorized_hunts": list(authorized_hunts),
                "visible_cases": visible_cases,
                "prior_case_context_included": False,
                "group": group.model_dump(mode="json"),
            }
        )
    )


def build_collaboration_request(
    *,
    run_key: str,
    prompt: str,
    schema: Mapping[str, Any],
    sources: Mapping[str, MaterializedSource],
    runtime_source_sha256: str,
    authorized_hunts: Sequence[str],
    visible_cases: int,
    group: CollaborationGroupIdentity,
) -> CollaborationSubagentRequest:
    schema_payload = dict(schema)
    model_visible_prompt = self_contained_collaboration_prompt(prompt, schema_payload)
    source_hashes = {
        alias: source.source_sha256 for alias, source in sorted(sources.items())
    }
    return CollaborationSubagentRequest(
        run_key=run_key,
        request_sha256=collaboration_request_sha256(
            run_key=run_key,
            prompt=model_visible_prompt,
            schema=schema_payload,
            source_sha256=source_hashes,
            runtime_source_sha256=runtime_source_sha256,
            authorized_hunts=authorized_hunts,
            visible_cases=visible_cases,
            group=group,
        ),
        prompt=model_visible_prompt,
        prompt_sha256=_sha_bytes(model_visible_prompt.encode("utf-8")),
        response_schema=schema_payload,
        schema_sha256=_sha_bytes(_canonical_bytes(schema_payload)),
        source_sha256=source_hashes,
        runtime_source_sha256=runtime_source_sha256,
        authorized_hunts=tuple(authorized_hunts),
        visible_cases=visible_cases,
        group=group,
    )


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _ensure_immutable_json(path: Path, model: BaseModel) -> None:
    """Write one JSON artifact, or require an existing artifact to be identical."""

    rendered = model.model_dump_json(indent=2)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"invalid partial collaboration artifact: {path}") from exc
        if existing != model.model_dump(mode="json"):
            raise RuntimeError(
                f"refusing to replace partial collaboration artifact: {path}"
            )
        return
    _atomic_write(path, rendered)


def ensure_collaboration_request(
    path: Path, request: CollaborationSubagentRequest
) -> None:
    """Write one request once, or verify its exact existing identity for resume."""

    path = Path(path)
    if path.exists():
        prior = CollaborationSubagentRequest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if prior != request:
            raise RuntimeError("collaboration request differs from existing artifact")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, request.model_dump_json(indent=2))


def _require_adaptive_observation(
    *, request: CollaborationSubagentRequest, tool_logs: Sequence[ToolLogEntry]
) -> None:
    """Reject adaptive captures that cannot support an evidence decision."""

    if ADAPTIVE_HUNT not in request.authorized_hunts:
        return
    if any(
        log.hunt == ADAPTIVE_HUNT
        and log.error is None
        and bool(log.observation_summary)
        for log in tool_logs
    ):
        return
    raise ValueError(
        "adaptive collaboration capture requires at least one successful "
        "staged observation"
    )


def seal_collaboration_subagent_output(
    *,
    request: CollaborationSubagentRequest,
    submission: CollaborationSubagentSubmission | CollaborationSubagentSubmissionV2,
    response_model: type[BaseModel],
    artifact_dir: Path,
    key: str,
) -> CollaborationSubagentExecutionV2:
    """Seal a v2 capture without inventing unavailable resource telemetry."""

    if not isinstance(submission, CollaborationSubagentSubmissionV2):
        raise TypeError("collaboration submission-v1 is load-only")
    if request.schema_version != REQUEST_SCHEMA_V2:
        raise ValueError("collaboration request-v1 is load-only")
    if key != request.run_key or submission.request_sha256 != request.request_sha256:
        raise ValueError("collaboration submission differs from frozen request")
    if submission.group != request.group:
        raise ValueError("collaboration submission differs from frozen group")
    response_model.model_validate_json(submission.final_json)
    if any(log.hunt not in request.authorized_hunts for log in submission.tool_logs):
        raise ValueError("collaboration submission contains an unauthorized hunt log")
    event_payload = [event.model_dump(mode="json") for event in submission.events]
    logs = list(submission.tool_logs)
    _require_adaptive_observation(request=request, tool_logs=logs)
    usage = (
        submission.usage_evidence.as_codex_usage()
        if isinstance(submission.usage_evidence, ReportedCollaborationUsage)
        else None
    )
    resource_valid = (
        submission.usage_evidence.status == "reported"
        and submission.timing_evidence.status == "reported"
    )
    execution = CollaborationSubagentExecutionV2(
        capture_source=submission.capture_source,
        request=request,
        task_name=submission.task_name,
        task_id=submission.task_id,
        group=submission.group,
        parsed=CollaborationParsedEventsV2(
            final_message=submission.final_json,
            usage=usage,
            thread_id=submission.task_id,
            events=event_payload,
        ),
        final_message=submission.final_json,
        usage_evidence=submission.usage_evidence,
        timing_evidence=submission.timing_evidence,
        evidence_scope=(
            "correctness_and_resources"
            if resource_valid
            else "descriptive_correctness_only"
        ),
        resource_evidence_valid=resource_valid,
        tool_logs=logs,
        request_sha256=request.request_sha256,
        event_stream_sha256=_sha_bytes(_canonical_bytes(event_payload)),
        tool_logs_sha256=_sha_bytes(
            _canonical_bytes([log.model_dump(mode="json") for log in logs])
        ),
        transcript_sha256=_sha_bytes(
            _canonical_bytes(
                {
                    "task_name": submission.task_name,
                    "task_id": submission.task_id,
                    "prompt": request.prompt,
                    "final_json": submission.final_json,
                    "events": event_payload,
                }
            )
        ),
    )
    target = Path(artifact_dir) / "raw" / key
    request_path = target / "request.json"
    execution_path = target / "execution.json"
    marker_path = target / "complete"
    marker = CollaborationBundleMarkerV2(
        key=key,
        request_sha256=request.request_sha256,
        request_artifact_sha256=_sha_bytes(_canonical_bytes(request)),
        execution_sha256=_sha_bytes(_canonical_bytes(execution)),
        event_stream_sha256=execution.event_stream_sha256,
        tool_logs_sha256=execution.tool_logs_sha256,
        transcript_sha256=execution.transcript_sha256,
        evidence_scope=execution.evidence_scope,
        resource_evidence_valid=execution.resource_evidence_valid,
    )
    if target.exists() and marker_path.is_file():
        prior = load_collaboration_bundle(
            artifact_dir=artifact_dir,
            key=key,
            expected_request_sha256=request.request_sha256,
        )
        if prior != execution:
            raise RuntimeError("refusing to overwrite immutable collaboration bundle")
        return prior
    target.mkdir(parents=True, exist_ok=True)
    _ensure_immutable_json(request_path, request)
    _ensure_immutable_json(execution_path, execution)
    # Completion remains last, so readers never consume a partially sealed bundle.
    _ensure_immutable_json(marker_path, marker)
    return execution


def load_collaboration_bundle(
    *, artifact_dir: Path, key: str, expected_request_sha256: str | None = None
) -> CollaborationSubagentExecution | CollaborationSubagentExecutionV2 | None:
    target = Path(artifact_dir) / "raw" / key
    request_path = target / "request.json"
    execution_path = target / "execution.json"
    marker_path = target / "complete"
    if not all(path.is_file() for path in (request_path, execution_path, marker_path)):
        return None
    request = CollaborationSubagentRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    execution_payload = json.loads(execution_path.read_text(encoding="utf-8"))
    is_v2 = (
        execution_payload.get("schema_version")
        == "configuration-3-collaboration-execution-v2"
    )
    execution: CollaborationSubagentExecution | CollaborationSubagentExecutionV2
    expected: CollaborationBundleMarker | CollaborationBundleMarkerV2
    if is_v2:
        execution = CollaborationSubagentExecutionV2.model_validate(execution_payload)
        marker = CollaborationBundleMarkerV2.model_validate_json(
            marker_path.read_text(encoding="utf-8")
        )
        expected = CollaborationBundleMarkerV2(
            key=key,
            request_sha256=request.request_sha256,
            request_artifact_sha256=_sha_bytes(_canonical_bytes(request)),
            execution_sha256=_sha_bytes(_canonical_bytes(execution)),
            event_stream_sha256=execution.event_stream_sha256,
            tool_logs_sha256=execution.tool_logs_sha256,
            transcript_sha256=execution.transcript_sha256,
            evidence_scope=execution.evidence_scope,
            resource_evidence_valid=execution.resource_evidence_valid,
        )
    else:
        execution = CollaborationSubagentExecution.model_validate(execution_payload)
        marker = CollaborationBundleMarker.model_validate_json(
            marker_path.read_text(encoding="utf-8")
        )
        expected = CollaborationBundleMarker(
            key=key,
            request_sha256=request.request_sha256,
            request_artifact_sha256=_sha_bytes(_canonical_bytes(request)),
            execution_sha256=_sha_bytes(_canonical_bytes(execution)),
            event_stream_sha256=execution.event_stream_sha256,
            tool_logs_sha256=execution.tool_logs_sha256,
            transcript_sha256=execution.transcript_sha256,
        )
    if marker != expected or execution.request != request:
        raise ValueError(f"collaboration raw bundle hash mismatch for {key}")
    if (
        expected_request_sha256 is not None
        and execution.request_sha256 != expected_request_sha256
    ):
        raise ValueError(f"collaboration request identity mismatch for {key}")
    return execution
