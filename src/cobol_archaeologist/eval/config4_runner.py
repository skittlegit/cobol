"""Provider-free configuration-4 preparation, sealing, and resume helpers.

This layer mirrors the configuration-3 request/staging protocol while keeping
all successor artifacts under the configuration-4 root.  It never starts a
provider process.  A full request set may only be prepared after the exact
all-system smoke receipt has passed; callers supply full rows after that gate
so this module does not open a hidden-test file while the gate is closed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.eval.codex_batch import (
    CodexBaselineEnvelope,
    CodexBatchEnvelope,
    strict_codex_schema,
)
from cobol_archaeologist.eval.codex_tool import ADAPTIVE_HUNT, AGENT_HUNTS
from cobol_archaeologist.eval.collaboration_staging import (
    StagedCollaborationTask,
    load_staged_tool_logs,
    stage_collaboration_task,
)
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationGroupIdentity,
    CollaborationSubagentExecutionV2,
    CollaborationSubagentRequest,
    CollaborationSubagentSubmissionV2,
    CollaborationTranscriptEvent,
    build_collaboration_request,
    collaboration_completion_receipt_payload,
    collaboration_start_receipt_payload,
    collaboration_tool_receipt_payload,
    ensure_collaboration_request,
    load_collaboration_bundle,
    seal_collaboration_subagent_output,
)
from cobol_archaeologist.eval.config3_controls import build_control_contexts
from cobol_archaeologist.eval.config3_live import (
    PHASE5_AGGREGATE_PATHS,
    PHASE5_BASELINE_PATHS,
    CodexAdaptiveEnvelope,
    _load_split,
    build_adaptive_codex_prompt,
    build_agent_prompt,
    build_baseline_prompt,
)
from cobol_archaeologist.eval.config4_live import (
    CONFIG4_SYSTEMS,
    Config4Progress,
    Config4RunFreeze,
    Config4RunMode,
    _atomic_write,
    _guard_config4_output,
    _resolve_path,
    config4_run_key,
    ensure_config4_frozen_identity,
    require_config4_full_smoke_readiness,
)
from cobol_archaeologist.eval.config4_live import (
    canonical_sha256 as config4_canonical_sha256,
)
from cobol_archaeologist.eval.materialize import MaterializedSource, materialize
from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.schemas import DriftInstance

CONFIG4_REQUEST_DIRECTORY = "requests"
CONFIG4_STAGING_DIRECTORY = "task-staging"
CONFIG4_PREPARATION_NAME = "run-preparation.json"
CONFIG4_MAX_WORKERS = 3
Config4ControlID = Literal[
    "agent", "plain_llm", "rag_dense", "rag_reranker", "oracle_slice"
]


class Config4PreparedTask(BaseModel):
    """One exact successor request and its optional bounded staging tree."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    schema_version: Literal["configuration-4-prepared-task-v1"] = (
        "configuration-4-prepared-task-v1"
    )
    configuration: Literal[4] = 4
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_id: str
    run_mode: Config4RunMode
    ordinal: int = Field(ge=1)
    task_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_instance_ids: tuple[str, ...] = Field(min_length=1)
    row_run_keys: tuple[str, ...] = Field(min_length=1)
    request_path: Path
    artifact_dir: Path
    staging_base: Path | None
    staging_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tool_command: str | None = None
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_cases: int = Field(ge=1)


class Config4RunPreparation(BaseModel):
    """Immutable provider-free roster of one smoke or full request set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-run-preparation-v1"] = (
        "configuration-4-run-preparation-v1"
    )
    configuration: Literal[4] = 4
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_mode: Config4RunMode
    systems: tuple[str, ...]
    row_order: tuple[str, ...]
    task_count: int = Field(ge=1)
    provider_calls_performed: Literal[0] = 0
    tasks: tuple[Config4PreparedTask, ...] = Field(min_length=1)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, model.model_dump_json(indent=2))


def validate_config4_phase5_baseline_identity(
    freeze: Config4RunFreeze, *, root: Path
) -> None:
    """Retain config3's deterministic Phase-5 artifact pins for the successor."""

    root = Path(root).resolve()
    actual_baselines = {
        relative.as_posix(): _sha(root / relative)
        for relative in PHASE5_BASELINE_PATHS
    }
    actual_aggregates = {
        relative.as_posix(): _sha(root / relative)
        for relative in PHASE5_AGGREGATE_PATHS
    }
    if actual_baselines != freeze.phase5_baseline_sha256:
        raise RuntimeError("configuration-4 Phase-5 baseline identity differs")
    if actual_aggregates != freeze.phase5_aggregate_sha256:
        raise RuntimeError("configuration-4 Phase-5 aggregate identity differs")


def load_config4_smoke_rows(
    freeze: Config4RunFreeze, *, root: Path
) -> list[DriftInstance]:
    """Load only the frozen train/dev smoke roster; never the held-out split."""

    root = Path(root).resolve()
    dev = _load_split(root / freeze.dev_split_path)
    train = _load_split(root / freeze.train_split_path)
    by_id = {row.instance_id: row for row in (*dev, *train)}
    missing = [
        instance_id
        for instance_id in freeze.smoke_instance_ids
        if instance_id not in by_id
    ]
    if missing:
        raise RuntimeError("configuration-4 smoke roster is not in train/dev")
    return [by_id[instance_id] for instance_id in freeze.smoke_instance_ids]


def _expected_rows(
    *, freeze: Config4RunFreeze, rows: Sequence[DriftInstance], mode: Config4RunMode
) -> None:
    expected = freeze.smoke_instance_ids if mode == "smoke" else freeze.test_order
    if tuple(row.instance_id for row in rows) != tuple(expected):
        raise ValueError(f"configuration-4 {mode} rows differ from the frozen order")


def _chunks[T](values: Sequence[T], size: int) -> list[list[T]]:
    if size < 1:
        raise ValueError("configuration-4 task batch size must be positive")
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


def config4_task_key(
    *,
    freeze: Config4RunFreeze,
    system_id: str,
    run_mode: Config4RunMode,
    row_run_keys: Sequence[str],
) -> str:
    if not row_run_keys:
        raise ValueError("configuration-4 task cannot be empty")
    return config4_canonical_sha256(
        {
            "configuration": 4,
            "freeze_sha256": config4_canonical_sha256(freeze),
            "system_id": system_id,
            "run_mode": run_mode,
            "row_run_keys": list(row_run_keys),
        }
    )


def _response_model(system_id: str) -> type[BaseModel]:
    if system_id == "adaptive_agent":
        return CodexAdaptiveEnvelope
    if system_id == "agent":
        return CodexBatchEnvelope
    return CodexBaselineEnvelope


def _authorized_hunts(system_id: str) -> tuple[str, ...]:
    if system_id == "adaptive_agent":
        return (ADAPTIVE_HUNT,)
    if system_id == "agent":
        return tuple(AGENT_HUNTS)
    return ()


def _aliases(batch: Sequence[DriftInstance]) -> tuple[str, ...]:
    return tuple(f"drift_{900000 + index:06d}" for index in range(len(batch)))


def _build_prompt_parts(
    *,
    system_id: str,
    batch: Sequence[DriftInstance],
    sources: Mapping[str, MaterializedSource],
    contexts: Mapping[str, BaseModel],
    tool_command: str | None,
) -> tuple[str, dict[str, Any], dict[str, MaterializedSource]]:
    aliases = _aliases(batch)
    alias_rows = dict(zip(aliases, batch, strict=True))
    if system_id == "adaptive_agent":
        if len(batch) != 1 or tool_command is None:
            raise ValueError("configuration-4 adaptive tasks require one staged case")
        row = batch[0]
        prompt = build_adaptive_codex_prompt(
            alias=aliases[0],
            clause=row.regulation_clause,
            program_scope=Path(row.provenance.base_program).stem,
            tool_command=tool_command,
        )
        return (
            prompt,
            strict_codex_schema(CodexAdaptiveEnvelope),
            {aliases[0]: sources[row.instance_id]},
        )
    if system_id == "agent":
        if tool_command is None:
            raise ValueError("configuration-4 agent tasks require staged tools")
        prompt = build_agent_prompt(
            [
                {
                    "alias": alias,
                    "program_scope": Path(row.provenance.base_program).stem,
                    "clause": row.regulation_clause.model_dump(mode="json"),
                }
                for alias, row in alias_rows.items()
            ],
            tool_command=tool_command,
        )
        return (
            prompt,
            strict_codex_schema(CodexBatchEnvelope),
            {
                alias: sources[row.instance_id]
                for alias, row in alias_rows.items()
            },
        )
    prompt = build_baseline_prompt(
        system_id,
        [
            {"alias": alias, "context": contexts[row.instance_id].model_dump(mode="json")}
            for alias, row in alias_rows.items()
        ],
    )
    return prompt, strict_codex_schema(CodexBaselineEnvelope), {}


def _initial_progress(
    *, freeze: Config4RunFreeze, mode: Config4RunMode, system_id: str, rows: Sequence[DriftInstance]
) -> Config4Progress:
    return Config4Progress(
        freeze_sha256=config4_canonical_sha256(freeze),
        system_id=system_id,
        run_mode=mode,
        completed_run_keys=[],
        pending_instance_ids=[row.instance_id for row in rows],
        interruptions={},
        status="IN_PROGRESS",
    )


def _load_or_write_initial_progress(
    *, output_dir: Path, freeze: Config4RunFreeze, mode: Config4RunMode,
    system_id: str, rows: Sequence[DriftInstance]
) -> Config4Progress:
    path = output_dir / mode / system_id / "progress.json"
    initial = _initial_progress(
        freeze=freeze, mode=mode, system_id=system_id, rows=rows
    )
    if path.exists():
        prior = Config4Progress.model_validate_json(path.read_text(encoding="utf-8"))
        if (
            prior.configuration != 4
            or prior.freeze_sha256 != initial.freeze_sha256
            or prior.system_id != system_id
            or prior.run_mode != mode
            or set(prior.pending_instance_ids) - set(initial.pending_instance_ids)
        ):
            raise RuntimeError("configuration-4 progress differs from frozen roster")
        return prior
    _atomic_json(path, initial)
    return initial


def prepare_config4_run(
    *,
    freeze: Config4RunFreeze,
    rows: Sequence[DriftInstance],
    mode: Config4RunMode,
    output_dir: Path | str | None = None,
    root: Path,
    regulation_search: RegulationSearch | None = None,
    context_builder: Callable[..., Mapping[str, BaseModel]] | None = None,
) -> Config4RunPreparation:
    """Prepare exact successor requests/staging without invoking a provider."""

    if freeze.configuration != 4:
        raise ValueError("configuration-4 preparation requires a configuration-4 freeze")
    if freeze.max_workers > CONFIG4_MAX_WORKERS:
        raise ValueError("configuration-4 max_workers exceeds the three-task cap")
    root = Path(root).resolve()
    output = _resolve_path(
        output_dir if output_dir is not None else freeze.output_root, root=root
    )
    _guard_config4_output(output, root=root)
    if mode == "full":
        # This is intentionally first: callers must not materialize or inspect
        # held-out rows before the all-system smoke receipt is current.
        require_config4_full_smoke_readiness(output_dir=output, freeze=freeze)
    ensure_config4_frozen_identity(output / "run-freeze.json", freeze, root=root)
    _expected_rows(freeze=freeze, rows=rows, mode=mode)
    validate_config4_phase5_baseline_identity(freeze, root=root)
    sources = {row.instance_id: materialize(row) for row in rows}
    for row in rows:
        if freeze.source_sha256.get(row.instance_id) != sources[row.instance_id].source_sha256:
            raise RuntimeError(f"configuration-4 source hash differs for {row.instance_id}")
    tasks: list[Config4PreparedTask] = []
    for system_id in CONFIG4_SYSTEMS:
        _load_or_write_initial_progress(
            output_dir=output,
            freeze=freeze,
            mode=mode,
            system_id=system_id,
            rows=rows,
        )
        batch_size = freeze.batch_sizes.get(system_id)
        if batch_size is None:
            raise RuntimeError(f"configuration-4 freeze has no batch size for {system_id}")
        if system_id == "adaptive_agent" and batch_size != 1:
            raise ValueError("configuration-4 adaptive tasks must have batch size one")
        batches = _chunks(rows, batch_size)
        contexts: Mapping[str, BaseModel] = {}
        if system_id not in {"agent", "adaptive_agent"}:
            if context_builder is not None:
                contexts = context_builder(
                    system_id,
                    rows=rows,
                    sources=sources,
                    regulation_search=regulation_search,
                )
            else:
                contexts = build_control_contexts(
                    system_id,
                    rows=rows,
                    sources=sources,
                    regulation_search=regulation_search,
                )
        artifact_dir = output / mode / system_id
        staging_base = artifact_dir / CONFIG4_STAGING_DIRECTORY
        request_dir = artifact_dir / CONFIG4_REQUEST_DIRECTORY
        for ordinal, batch in enumerate(batches, start=1):
            row_run_keys = tuple(
                config4_run_key(
                    freeze=freeze,
                    system_id=system_id,  # type: ignore[arg-type]
                    run_mode=mode,
                    instance_id=row.instance_id,
                    source_sha256=sources[row.instance_id].source_sha256,
                )
                for row in batch
            )
            task_key = row_run_keys[0] if system_id == "adaptive_agent" else config4_task_key(
                freeze=freeze,
                system_id=system_id,
                run_mode=mode,
                row_run_keys=row_run_keys,
            )
            staged: StagedCollaborationTask | None = None
            if system_id in {"agent", "adaptive_agent"}:
                staged = stage_collaboration_task(
                    staging_base=staging_base,
                    run_key=task_key,
                    sources={
                        alias: sources[row.instance_id]
                        for alias, row in zip(_aliases(batch), batch, strict=True)
                    },
                    authorized_hunts=_authorized_hunts(system_id),
                )
            prompt, schema, task_sources = _build_prompt_parts(
                system_id=system_id,
                batch=batch,
                sources=sources,
                contexts=contexts,
                tool_command=staged.tool_command if staged is not None else None,
            )
            request = build_collaboration_request(
                run_key=task_key,
                prompt=prompt,
                schema=schema,
                sources=task_sources,
                runtime_source_sha256=freeze.runtime_source_sha256,
                authorized_hunts=_authorized_hunts(system_id),
                visible_cases=len(batch),
                group=CollaborationGroupIdentity(
                    group_id=f"config4:{mode}:{system_id}",
                    mode="concurrent" if len(batches) > 1 else "sequential",
                    ordinal=ordinal,
                    size=len(batches),
                ),
            )
            request_path = request_dir / f"{task_key}.json"
            ensure_collaboration_request(request_path, request)
            tasks.append(
                Config4PreparedTask(
                    freeze_sha256=config4_canonical_sha256(freeze),
                    system_id=system_id,
                    run_mode=mode,
                    ordinal=ordinal,
                    task_key=task_key,
                    row_instance_ids=tuple(row.instance_id for row in batch),
                    row_run_keys=row_run_keys,
                    request_path=request_path,
                    artifact_dir=artifact_dir,
                    staging_base=staging_base if staged is not None else None,
                    staging_sha256=staged.staging_sha256 if staged is not None else None,
                    tool_command=staged.tool_command if staged is not None else None,
                    request_sha256=request.request_sha256,
                    prompt_sha256=request.prompt_sha256,
                    schema_sha256=request.schema_sha256,
                    visible_cases=len(batch),
                )
            )
    preparation = Config4RunPreparation(
        freeze_sha256=config4_canonical_sha256(freeze),
        run_mode=mode,
        systems=tuple(CONFIG4_SYSTEMS),
        row_order=tuple(row.instance_id for row in rows),
        task_count=len(tasks),
        tasks=tuple(tasks),
    )
    preparation_path = output / mode / CONFIG4_PREPARATION_NAME
    if preparation_path.exists():
        prior = Config4RunPreparation.model_validate_json(
            preparation_path.read_text(encoding="utf-8")
        )
        if prior != preparation:
            raise RuntimeError("configuration-4 request preparation differs")
    else:
        _atomic_json(preparation_path, preparation)
    return preparation


def update_config4_progress(
    *,
    freeze: Config4RunFreeze,
    output_dir: Path | str,
    mode: Config4RunMode,
    system_id: str,
    completed_run_keys: Sequence[str],
    pending_instance_ids: Sequence[str],
    interruptions: Mapping[str, str],
) -> Config4Progress:
    """Persist one resumable system progress record with frozen identity checks."""

    output = _resolve_path(output_dir)
    _guard_config4_output(output)
    expected_ids = freeze.smoke_instance_ids if mode == "smoke" else freeze.test_order
    expected = {
        config4_run_key(
            freeze=freeze,
            system_id=system_id,  # type: ignore[arg-type]
            run_mode=mode,
            instance_id=instance_id,
            source_sha256=freeze.source_sha256[instance_id],
        )
        for instance_id in expected_ids
    }
    if not set(completed_run_keys).issubset(expected):
        raise ValueError("configuration-4 progress contains an unexpected run key")
    status = (
        "VALID"
        if not pending_instance_ids and not interruptions and set(completed_run_keys) == expected
        else "IN_PROGRESS"
    )
    progress = Config4Progress(
        freeze_sha256=config4_canonical_sha256(freeze),
        system_id=system_id,
        run_mode=mode,
        completed_run_keys=sorted(completed_run_keys),
        pending_instance_ids=list(pending_instance_ids),
        interruptions=dict(interruptions),
        status=status,
    )
    _atomic_json(output / mode / system_id / "progress.json", progress)
    return progress


def _task_request(task: Config4PreparedTask) -> CollaborationSubagentRequest:
    request = CollaborationSubagentRequest.model_validate_json(
        task.request_path.read_text(encoding="utf-8")
    )
    if request.run_key != task.task_key or request.request_sha256 != task.request_sha256:
        raise ValueError("configuration-4 prepared request identity differs")
    return request


def seal_config4_capture(
    *,
    task: Config4PreparedTask,
    final_json: str,
    task_name: str,
    task_id: str,
) -> CollaborationSubagentExecutionV2:
    """Seal one externally supplied final and preserve exact host staging."""

    request = _task_request(task)
    logs = (
        load_staged_tool_logs(
            staging_base=task.staging_base,
            run_key=task.task_key,
            expected_staging_sha256=task.staging_sha256,
        )
        if task.staging_base is not None and task.staging_sha256 is not None
        else ()
    )
    final_sha256 = hashlib.sha256(final_json.encode("utf-8")).hexdigest()
    events = [
        CollaborationTranscriptEvent(
            sequence=1,
            type="task.started",
            task_name=task_name,
            payload=collaboration_start_receipt_payload(
                task_id=task_id, request_sha256=request.request_sha256
            ),
        )
    ]
    events.extend(
        CollaborationTranscriptEvent(
            sequence=sequence,
            type="tool.completed",
            task_name=task_name,
            payload=collaboration_tool_receipt_payload(
                task_id=task_id, request_sha256=request.request_sha256, log=log
            ),
        )
        for sequence, log in enumerate(logs, start=2)
    )
    events.append(
        CollaborationTranscriptEvent(
            sequence=len(events) + 1,
            type="task.completed",
            task_name=task_name,
            payload=collaboration_completion_receipt_payload(
                task_id=task_id,
                request_sha256=request.request_sha256,
                final_sha256=final_sha256,
            ),
        )
    )
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
        tool_logs=logs,
        events=tuple(events),
    )
    return seal_collaboration_subagent_output(
        request=request,
        submission=submission,
        response_model=_response_model(task.system_id),
        artifact_dir=task.artifact_dir,
        key=task.task_key,
    )


def replay_config4_capture(
    *, task: Config4PreparedTask
) -> CollaborationSubagentExecutionV2:
    """Load and validate one sealed successor bundle for deterministic replay."""

    request = _task_request(task)
    execution = load_collaboration_bundle(
        artifact_dir=task.artifact_dir,
        key=task.task_key,
        expected_request_sha256=request.request_sha256,
    )
    if not isinstance(execution, CollaborationSubagentExecutionV2):
        raise TypeError("configuration-4 sealed capture is missing or not v2")
    if execution.request != request:
        raise ValueError("configuration-4 sealed capture request differs")
    if task.staging_base is not None and task.staging_sha256 is not None:
        from cobol_archaeologist.eval.config3_live import (
            validate_staged_collaboration_execution,
        )

        validate_staged_collaboration_execution(
            execution,
            staged=StagedCollaborationTask(
                task_root=task.staging_base / task.task_key,
                run_key=task.task_key,
                staging_sha256=task.staging_sha256,
                tool_command=task.tool_command or "",
            ),
            staging_base=task.staging_base,
        )
    return execution
