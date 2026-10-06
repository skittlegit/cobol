"""Frozen Luna/max controls for the configuration-3 evaluation.

The candidate adaptive agent has a batch-size-one runner in
``config3_live``.  This module runs the five provider controls under the same
run freeze while preserving their historical methods.  Provider workers only
return raw executions; the coordinator owns every durable evaluation write.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.eval.baselines import (
    RAG_RETRIEVAL_MODES,
    oracle_slice_context,
    plain_llm_context,
    rag_baseline_context,
)
from cobol_archaeologist.eval.codex_batch import (
    AGENT_HUNTS,
    CodexBaselineEnvelope,
    CodexBatchEnvelope,
    allocate_tokens,
    bind_submitted_response,
    finalize_agent_case,
    strict_codex_schema,
    validate_agent_envelope,
    validate_baseline_envelope,
)
from cobol_archaeologist.eval.codex_live import (
    DEFAULT_CODEX_BINARY,
    DEFAULT_WSL_DISTRO,
    CodexTaskExecution,
    _baseline_context,
    _check_chatgpt_login,
    _ReplayDecisionModel,
    _require_ok,
    _tool_layer,
    _wsl,
    _wsl_chatgpt_account_sha256,
    batch_size_for,
    build_agent_prompt,
    build_baseline_prompt,
    execute_codex_task,
    prepare_support_runtime,
    select_baseline_clause,
)
from cobol_archaeologist.eval.collaboration_staging import (
    StagedCollaborationTask,
    stage_collaboration_task,
)
from cobol_archaeologist.eval.collaboration_transport import (
    REQUEST_DIRECTORY_V2,
    CollaborationGroupIdentity,
    build_collaboration_request,
    ensure_collaboration_request,
)
from cobol_archaeologist.eval.config3_live import (
    COLLABORATION_STAGED_REQUEST_DIRECTORY,
    COLLABORATION_STAGING_DIRECTORY,
    DEFAULT_MAX_WORKERS,
    MODEL_ID,
    OUTPUT_DIR,
    REASONING_EFFORT,
    Config3Progress,
    Config3RunFreeze,
    ProviderTaskExecution,
    _atomic_write,
    _load_record_sidecars,
    _validate_record_raw_chain,
    _write_canonical_records,
    _write_record_sidecar,
    bounded_provider_map,
    canonical_sha256,
    config3_run_key,
    ensure_frozen_identity,
    expected_codex_request_sha256,
    freeze_path_for_transport,
    load_execution_bundle,
    persist_execution_bundle,
    refresh_smoke_readiness,
    require_full_smoke_readiness,
    runtime_source_sha256,
    validate_phase5_baseline_identity,
    validate_staged_collaboration_execution,
)
from cobol_archaeologist.eval.live import (
    AGENT_BUDGET,
    BASELINE_BUDGET,
    MIN_AGENT_ABSTENTION_OBSERVATIONS,
    bounded_code_context,
    single_shot_record,
)
from cobol_archaeologist.eval.materialize import MaterializedSource, materialize
from cobol_archaeologist.eval.run import record_outcome, repository_commit
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.verify import Entailer, default_entailer
from cobol_archaeologist.rag.search import RegulationSearch
from cobol_archaeologist.schemas import DriftInstance

ControlSystemID = Literal[
    "agent",
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
]
ControlRunMode = Literal["smoke", "full"]
CONTROL_SYSTEMS: tuple[ControlSystemID, ...] = (
    "agent",
    "plain_llm",
    "rag_dense",
    "rag_reranker",
    "oracle_slice",
)


class ControlRunSeal(BaseModel):
    """Exact control grouping and inputs sealed before provider execution."""

    model_config = ConfigDict(extra="forbid")

    configuration: Literal[3] = 3
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: Literal["collaboration_subagent", "chatgpt-codex"]
    authentication: Literal["in_product_orchestration", "ChatGPT"]
    transport: Literal["collaboration_subagent", "wsl", "native"]
    model_id: Literal["gpt-5.6-luna"] = MODEL_ID
    reasoning_effort: Literal["max"] = REASONING_EFFORT
    system_id: ControlSystemID
    run_mode: ControlRunMode
    budget: dict[str, Any]
    batch_size: int = Field(ge=1)
    row_order: tuple[str, ...]
    row_run_keys: tuple[str, ...]
    batch_run_keys: tuple[str, ...]
    source_sha256: dict[str, str]
    context_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    codex_live_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    codex_batch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _expected_budget(system_id: ControlSystemID):
    return AGENT_BUDGET if system_id == "agent" else BASELINE_BUDGET


def _chunks[T](values: Sequence[T], size: int) -> list[list[T]]:
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


def control_batch_key(
    *,
    freeze: Config3RunFreeze,
    system_id: ControlSystemID,
    mode: ControlRunMode,
    row_run_keys: Sequence[str],
) -> str:
    """Identify a predetermined provider batch without depending on resume state."""

    if not row_run_keys:
        raise ValueError("a control batch cannot be empty")
    return canonical_sha256(
        {
            "freeze_sha256": canonical_sha256(freeze),
            "system_id": system_id,
            "run_mode": mode,
            "row_run_keys": list(row_run_keys),
        }
    )


def build_control_contexts(
    system_id: ControlSystemID,
    *,
    rows: Sequence[DriftInstance],
    sources: Mapping[str, MaterializedSource],
    regulation_search: RegulationSearch | None = None,
) -> dict[str, BaseModel]:
    """Build deterministic, method-specific contexts before the run is sealed."""

    if system_id == "agent":
        return {}
    if system_id in RAG_RETRIEVAL_MODES:
        expected_mode = RAG_RETRIEVAL_MODES[system_id]
        search = regulation_search or RegulationSearch(mode=expected_mode)
        if search.mode != expected_mode:
            raise ValueError(
                f"{system_id} requires retrieval_mode={expected_mode!r}, "
                f"got {search.mode!r}"
            )
        return {
            row.instance_id: rag_baseline_context(
                system_id,
                row.regulation_clause.text,
                program=bounded_code_context(
                    sources[row.instance_id], row.regulation_clause.text
                ),
                search=search,
            )
            for row in rows
        }
    if system_id == "plain_llm":
        return {
            row.instance_id: plain_llm_context(
                row.regulation_clause,
                program=bounded_code_context(
                    sources[row.instance_id], row.regulation_clause.text
                ),
            )
            for row in rows
        }
    contexts: dict[str, BaseModel] = {}
    for row in rows:
        with tempfile.TemporaryDirectory(prefix="m4-config3-oracle-context-") as temp:
            tools = _tool_layer(sources[row.instance_id], Path(temp), None)
            contexts[row.instance_id] = oracle_slice_context(row, tools=tools)
    return contexts


def build_control_seal(
    *,
    freeze: Config3RunFreeze,
    system_id: ControlSystemID,
    mode: ControlRunMode,
    rows: Sequence[DriftInstance],
    sources: Mapping[str, MaterializedSource],
    contexts: Mapping[str, BaseModel],
) -> ControlRunSeal:
    """Bind exact rows, contexts, source, method code, budget, and grouping."""

    row_keys = tuple(
        config3_run_key(
            freeze=freeze,
            system_id=system_id,
            run_mode=mode,
            instance_id=row.instance_id,
            source_sha256=sources[row.instance_id].source_sha256,
        )
        for row in rows
    )
    batch_size = batch_size_for(system_id)
    batch_keys = tuple(
        control_batch_key(
            freeze=freeze,
            system_id=system_id,
            mode=mode,
            row_run_keys=group,
        )
        for group in _chunks(row_keys, batch_size)
    )
    module_dir = Path(__file__).resolve().parent
    return ControlRunSeal(
        freeze_sha256=canonical_sha256(freeze),
        provider=freeze.provider,
        authentication=freeze.authentication,
        transport=freeze.transport,
        system_id=system_id,
        run_mode=mode,
        budget=_expected_budget(system_id).model_dump(mode="json"),
        batch_size=batch_size,
        row_order=tuple(row.instance_id for row in rows),
        row_run_keys=row_keys,
        batch_run_keys=batch_keys,
        source_sha256={
            row.instance_id: sources[row.instance_id].source_sha256 for row in rows
        },
        context_sha256={
            instance_id: canonical_sha256(context)
            for instance_id, context in contexts.items()
        },
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        codex_live_sha256=hashlib.sha256(
            (module_dir / "codex_live.py").read_bytes()
        ).hexdigest(),
        codex_batch_sha256=hashlib.sha256(
            (module_dir / "codex_batch.py").read_bytes()
        ).hexdigest(),
    )


def ensure_control_seal(path: Path, seal: ControlRunSeal) -> str:
    """Persist a control seal once and reject method or grouping drift."""

    path = Path(path)
    if path.exists():
        prior = ControlRunSeal.model_validate_json(path.read_text(encoding="utf-8"))
        if prior != seal:
            raise RuntimeError(
                "configuration-3 control seal differs from existing file"
            )
    else:
        _atomic_write(path, seal.model_dump_json(indent=2))
    return canonical_sha256(seal)


def _validate_request(
    *,
    freeze: Config3RunFreeze,
    system_id: ControlSystemID,
    mode: ControlRunMode,
    rows: Sequence[DriftInstance],
    max_workers: int,
) -> None:
    if mode not in {"smoke", "full"}:
        raise ValueError("configuration 3 has no test pilot; use smoke or full")
    if system_id not in CONTROL_SYSTEMS or system_id not in freeze.systems:
        raise ValueError(f"{system_id!r} is not a frozen configuration-3 control")
    if max_workers != freeze.max_workers:
        raise ValueError("max_workers differs from the frozen run identity")
    expected_order = freeze.smoke_instance_ids if mode == "smoke" else freeze.test_order
    if tuple(row.instance_id for row in rows) != tuple(expected_order):
        raise ValueError("requested rows differ from the frozen row order")
    expected_budget = _expected_budget(system_id).model_dump(mode="json")
    if freeze.budgets.get(system_id) != expected_budget:
        raise ValueError(f"{system_id} budget differs from the historical method")
    if freeze.batch_sizes.get(system_id) != batch_size_for(system_id):
        raise ValueError(f"{system_id} batch size differs from the frozen method")


def _require_smoke_gate(
    *,
    output_dir: Path,
    freeze: Config3RunFreeze,
    system_id: ControlSystemID,
) -> None:
    require_full_smoke_readiness(
        output_dir=output_dir,
        freeze=freeze,
        system_id=system_id,
    )


def _persist_immutable_bundle(
    execution: ProviderTaskExecution,
    *,
    artifact_dir: Path,
    key: str,
    expected_request_sha256: str,
) -> None:
    existing = load_execution_bundle(
        artifact_dir=artifact_dir,
        key=key,
        expected_request_sha256=expected_request_sha256,
    )
    if existing is not None:
        if existing != execution:
            raise RuntimeError(f"refusing to overwrite immutable batch bundle {key}")
        return
    persist_execution_bundle(
        execution,
        artifact_dir=artifact_dir,
        key=key,
        expected_request_sha256=expected_request_sha256,
    )


def replay_baseline_batch(
    *,
    system_id: Literal["plain_llm", "rag_dense", "rag_reranker", "oracle_slice"],
    batch: Sequence[DriftInstance],
    execution: ProviderTaskExecution,
    sources: Mapping[str, MaterializedSource],
    contexts: Mapping[str, BaseModel],
    row_keys: Mapping[str, str],
    entailer: Entailer,
) -> list[EvaluationRecord]:
    """Host-replay one frozen baseline batch from its authorized raw execution."""

    if execution.tool_logs:
        raise ValueError("baseline raw execution contains unauthorized tool logs")
    aliases = [f"drift_{900000 + index:06d}" for index in range(len(batch))]
    alias_rows = dict(zip(aliases, batch, strict=True))
    envelope = CodexBaselineEnvelope.model_validate_json(execution.final_message)
    missing = validate_baseline_envelope(
        envelope,
        aliases,
        system_id=system_id,
        retrieved_counts={
            alias: len(
                contexts[row.instance_id]
                .model_dump(mode="json")
                .get("retrieved_clauses", [])
            )
            for alias, row in alias_rows.items()
        },
    )
    if missing:
        raise ValueError("baseline replay omitted a required alias")
    by_alias = {result.alias: result for result in envelope.results}
    usage_recorded = execution.parsed.usage is not None
    allocations = allocate_tokens(
        execution.parsed.usage.total_tokens if usage_recorded else 0,
        len(by_alias),
    )
    records: list[EvaluationRecord] = []
    for token_count, alias in zip(allocations, aliases, strict=True):
        row = alias_rows[alias]
        submitted = by_alias[alias]
        context = _baseline_context(
            system_id, contexts[row.instance_id].model_dump(mode="json")
        )
        clause = row.regulation_clause
        binding_error = None
        if submitted.response.kind == "finding":
            try:
                clause = select_baseline_clause(
                    system_id, submitted.clause_index, context
                )
            except (TypeError, ValueError) as exc:
                binding_error = str(exc)
        response = bind_submitted_response(
            submitted.response,
            instance_id=row.instance_id,
            clause=clause,
            token_count=token_count,
            token_count_recorded=usage_recorded,
            prebinding_error=binding_error,
        )
        with tempfile.TemporaryDirectory(prefix="m4-config3-reranker-replay-") as temp:
            tools = _tool_layer(sources[row.instance_id], Path(temp), None)
            records.append(
                single_shot_record(
                    row,
                    system_id=system_id,
                    source_sha256=sources[row.instance_id].source_sha256,
                    key=row_keys[row.instance_id],
                    context=context,
                    tools=tools,
                    model_factory=lambda response=response: _ReplayDecisionModel(
                        response, model_id=MODEL_ID
                    ),
                    entailer=entailer,
                )
            )
    return records


def replay_agent_batch(
    *,
    batch: Sequence[DriftInstance],
    execution: ProviderTaskExecution,
    sources: Mapping[str, MaterializedSource],
    row_keys: Mapping[str, str],
    entailer: Entailer,
) -> list[EvaluationRecord]:
    """Host-replay one frozen historical seven-hunt batch."""

    aliases = [f"drift_{900000 + index:06d}" for index in range(len(batch))]
    alias_rows = dict(zip(aliases, batch, strict=True))
    if any(
        log.alias not in alias_rows or log.hunt not in AGENT_HUNTS
        for log in execution.tool_logs
    ):
        raise ValueError("agent replay contains an unconsumed tool log")
    envelope = CodexBatchEnvelope.model_validate_json(execution.final_message)
    validate_agent_envelope(envelope, aliases)
    by_alias = {result.alias: result for result in envelope.results}
    usage_recorded = execution.parsed.usage is not None
    allocations = allocate_tokens(
        execution.parsed.usage.total_tokens if usage_recorded else 0,
        len(batch) * len(AGENT_HUNTS),
    )
    records: list[EvaluationRecord] = []
    for row_index, (alias, row) in enumerate(alias_rows.items()):
        with tempfile.TemporaryDirectory(prefix="m4-config3-agent-replay-") as temp:
            tools = _tool_layer(sources[row.instance_id], Path(temp), None)
            start = row_index * len(AGENT_HUNTS)
            outcome = finalize_agent_case(
                by_alias[alias],
                clause=row.regulation_clause,
                program_scope=Path(row.provenance.base_program).stem,
                instance_id=row.instance_id,
                logs=[log for log in execution.tool_logs if log.alias == alias],
                tools=tools,
                budget=AGENT_BUDGET,
                entailer=entailer,
                token_counts=allocations[start : start + len(AGENT_HUNTS)],
                token_counts_recorded=usage_recorded,
                min_successful_observations=MIN_AGENT_ABSTENTION_OBSERVATIONS,
                model_id=MODEL_ID,
            )
        records.append(
            record_outcome(
                row,
                outcome,
                system_id="agent",
                source_sha256=sources[row.instance_id].source_sha256,
                key=row_keys[row.instance_id],
            )
        )
    return records


def _write_progress(
    *,
    path: Path,
    freeze: Config3RunFreeze,
    system_id: ControlSystemID,
    mode: ControlRunMode,
    rows: Sequence[DriftInstance],
    records: Mapping[str, EvaluationRecord],
    row_keys: Mapping[str, str],
    interruptions: Mapping[str, str],
) -> Config3Progress:
    completed_ids = {record.instance_id for record in records.values()}
    pending = [row.instance_id for row in rows if row.instance_id not in completed_ids]
    complete = not pending and len(records) == len(rows)
    predictions = sum(record.prediction is not None for record in records.values())
    valid = complete and not interruptions and (system_id != "agent" or predictions > 0)
    progress = Config3Progress(
        freeze_sha256=canonical_sha256(freeze),
        system_id=system_id,
        run_mode=mode,
        completed_run_keys=sorted(records),
        pending_instance_ids=pending,
        interruptions=dict(interruptions),
        status="VALID" if valid else ("NOT_EVALUABLE" if complete else "IN_PROGRESS"),
    )
    if set(progress.completed_run_keys) - set(row_keys.values()):
        raise ValueError("progress contains a run key outside the frozen row set")
    _atomic_write(path, progress.model_dump_json(indent=2))
    return progress


def run_config3_control(
    system_id: ControlSystemID,
    *,
    rows: Sequence[DriftInstance],
    mode: ControlRunMode,
    freeze: Config3RunFreeze,
    output_dir: Path = OUTPUT_DIR,
    max_workers: int = DEFAULT_MAX_WORKERS,
    distro: str = DEFAULT_WSL_DISTRO,
    codex_binary: str = DEFAULT_CODEX_BINARY,
    transport: Literal["collaboration_subagent", "wsl", "native"] | None = None,
    native_codex_binary: str | None = None,
    entailer: Entailer | None = None,
    regulation_search: RegulationSearch | None = None,
    execution_function: Callable[..., CodexTaskExecution] | None = None,
) -> tuple[list[EvaluationRecord], Config3Progress]:
    """Run one frozen control with concurrent calls and coordinator finalization."""

    _validate_request(
        freeze=freeze,
        system_id=system_id,
        mode=mode,
        rows=rows,
        max_workers=max_workers,
    )
    transport = transport or freeze.transport
    if transport != freeze.transport:
        raise ValueError("transport differs from the frozen run identity")
    if mode == "full":
        _require_smoke_gate(
            output_dir=Path(output_dir), freeze=freeze, system_id=system_id
        )
    freeze_hash = ensure_frozen_identity(
        freeze_path_for_transport(output_dir=Path(output_dir), transport=transport),
        freeze,
    )
    repository_root = Path(__file__).resolve().parents[3]
    if runtime_source_sha256(repository_root) != freeze.runtime_source_sha256:
        raise RuntimeError(
            "runtime source snapshot differs from configuration-3 freeze"
        )
    validate_phase5_baseline_identity(freeze, root=repository_root)
    commit = repository_commit(repository_root)
    if commit != freeze.repository_commit:
        raise RuntimeError("repository commit differs from configuration-3 freeze")
    collaboration = transport == "collaboration_subagent"
    selected_execution: Callable[..., CodexTaskExecution] | None = None
    if collaboration:
        if execution_function is not None:
            raise ValueError(
                "collaboration_subagent accepts sealed external submissions, "
                "not a Codex execution function"
            )
        support_root = str(repository_root)
        tool_command = "python -m cobol_archaeologist.eval.codex_tool"
    elif transport == "native":
        from cobol_archaeologist.eval.codex_native import (
            execute_codex_task_native,
            native_chatgpt_account_sha256,
            native_codex_version,
            native_login_status,
            native_tool_command,
        )

        selected_binary = native_codex_binary or shutil.which("codex.exe")
        if selected_binary is None:
            raise RuntimeError("native codex.exe is not installed")
        login = native_login_status(selected_binary)
        account_sha256 = native_chatgpt_account_sha256()
        cli_version = native_codex_version(selected_binary)
        if freeze.wsl_distribution != "native-windows":
            raise RuntimeError("freeze execution environment is not native-windows")
        support_root = str(repository_root)
        tool_command = native_tool_command()
        selected_execution = execution_function or execute_codex_task_native
        codex_binary = selected_binary
        distro = "native-windows"
    else:
        login = _check_chatgpt_login(codex_binary=codex_binary, distro=distro)
        account_sha256 = _wsl_chatgpt_account_sha256(distro=distro)
        version = _wsl([codex_binary, "--version"], distro=distro)
        _require_ok(version, "read Codex CLI version")
        cli_version = version.stdout.decode("utf-8", errors="replace").strip()
        if freeze.wsl_distribution != distro:
            raise RuntimeError("WSL distribution differs from configuration-3 freeze")
        support_root = prepare_support_runtime(
            commit=freeze.runtime_source_sha256,
            distro=distro,
        )
        tool_command = (
            f"{support_root}/.venv/bin/python -m cobol_archaeologist.eval.codex_tool"
        )
        selected_execution = execution_function or execute_codex_task
    if not collaboration:
        if codex_binary != freeze.codex_binary:
            raise RuntimeError("Codex binary differs from configuration-3 freeze")
        if "ChatGPT" not in login:
            raise RuntimeError("ChatGPT authentication is required")
        if account_sha256 != freeze.chatgpt_account_sha256:
            raise RuntimeError("ChatGPT account differs from configuration-3 freeze")
        if cli_version != freeze.codex_cli_version:
            raise RuntimeError("Codex CLI version differs from configuration-3 freeze")
    sources = {row.instance_id: materialize(row) for row in rows}
    for row in rows:
        if (
            freeze.source_sha256.get(row.instance_id)
            != sources[row.instance_id].source_sha256
        ):
            raise RuntimeError(f"source hash differs from freeze for {row.instance_id}")
    contexts = build_control_contexts(
        system_id,
        rows=rows,
        sources=sources,
        regulation_search=regulation_search,
    )
    seal = build_control_seal(
        freeze=freeze,
        system_id=system_id,
        mode=mode,
        rows=rows,
        sources=sources,
        contexts=contexts,
    )
    artifact_dir = Path(output_dir) / mode / system_id
    ensure_control_seal(artifact_dir / "control-seal.json", seal)
    row_keys = dict(zip(seal.row_order, seal.row_run_keys, strict=True))
    batches = _chunks(list(rows), seal.batch_size)
    batch_keys = dict(
        zip(
            (batch[0].instance_id for batch in batches),
            seal.batch_run_keys,
            strict=True,
        )
    )
    row_to_batch_key = {
        row.instance_id: batch_keys[batch[0].instance_id]
        for batch in batches
        for row in batch
    }

    def prepare_batch(
        batch: Sequence[DriftInstance],
        *,
        selected_tool_command: str = tool_command,
    ) -> tuple[str, dict[str, Any], dict[str, MaterializedSource]]:
        aliases = [f"drift_{900000 + index:06d}" for index in range(len(batch))]
        alias_rows = dict(zip(aliases, batch, strict=True))
        if system_id == "agent":
            prompt = build_agent_prompt(
                [
                    {
                        "alias": alias,
                        "program_scope": Path(row.provenance.base_program).stem,
                        "clause": row.regulation_clause.model_dump(mode="json"),
                    }
                    for alias, row in alias_rows.items()
                ],
                tool_command=selected_tool_command,
            )
            schema = strict_codex_schema(CodexBatchEnvelope)
            task_sources = {
                alias: sources[row.instance_id] for alias, row in alias_rows.items()
            }
        else:
            prompt = build_baseline_prompt(
                system_id,
                [
                    {
                        "alias": alias,
                        "context": contexts[row.instance_id].model_dump(mode="json"),
                    }
                    for alias, row in alias_rows.items()
                ],
            )
            schema = strict_codex_schema(CodexBaselineEnvelope)
            task_sources = {}
        return prompt, schema, task_sources

    request_parts = {
        batch_keys[batch[0].instance_id]: prepare_batch(batch) for batch in batches
    }
    authorized_hunts = AGENT_HUNTS if system_id == "agent" else ()
    collaboration_requests = {}
    staged_tasks: dict[str, StagedCollaborationTask] = {}
    staging_base = artifact_dir / COLLABORATION_STAGING_DIRECTORY
    if collaboration:
        group_id = f"config3:{mode}:{system_id}"
        for ordinal, batch in enumerate(batches, start=1):
            batch_key = batch_keys[batch[0].instance_id]
            parts = request_parts[batch_key]
            request_directory = REQUEST_DIRECTORY_V2
            if system_id == "agent":
                staged = stage_collaboration_task(
                    staging_base=staging_base,
                    run_key=batch_key,
                    sources=parts[2],
                    authorized_hunts=authorized_hunts,
                )
                staged_tasks[batch_key] = staged
                parts = prepare_batch(
                    batch,
                    selected_tool_command=staged.tool_command,
                )
                request_parts[batch_key] = parts
                request_directory = COLLABORATION_STAGED_REQUEST_DIRECTORY
            request = build_collaboration_request(
                run_key=batch_key,
                prompt=parts[0],
                schema=parts[1],
                sources=parts[2],
                runtime_source_sha256=freeze.runtime_source_sha256,
                authorized_hunts=authorized_hunts,
                visible_cases=len(batch),
                group=CollaborationGroupIdentity(
                    group_id=group_id,
                    mode="concurrent" if len(batches) > 1 else "sequential",
                    ordinal=ordinal,
                    size=len(batches),
                ),
            )
            ensure_collaboration_request(
                artifact_dir / request_directory / f"{batch_key}.json", request
            )
            collaboration_requests[batch_key] = request
        expected_requests = {
            key: request.request_sha256
            for key, request in collaboration_requests.items()
        }
    else:
        expected_requests = {
            batch_key: expected_codex_request_sha256(
                prompt=parts[0],
                schema=parts[1],
                sources=parts[2],
                transport=transport,
                codex_binary=codex_binary,
                runtime_source_sha256=freeze.runtime_source_sha256,
                chatgpt_account_sha256=freeze.chatgpt_account_sha256,
                authorized_hunts=authorized_hunts,
            )
            for batch_key, parts in request_parts.items()
        }
    sidecar_dir = artifact_dir / "records"
    records, sidecar_markers = _load_record_sidecars(sidecar_dir)
    if set(records) - set(row_keys.values()):
        raise ValueError("record sidecars contain stale or unexpected run keys")
    for record in records.values():
        if (
            record.system_id != system_id
            or row_keys.get(record.instance_id) != record.run_key
            or record.source_sha256 != sources[record.instance_id].source_sha256
            or record.gold
            != next(row for row in rows if row.instance_id == record.instance_id)
        ):
            raise ValueError("record sidecar identity differs from the control seal")
    if records:
        _validate_record_raw_chain(
            records=records,
            markers=sidecar_markers,
            artifact_dir=artifact_dir,
            raw_keys_by_run_key={
                key: row_to_batch_key[record.instance_id]
                for key, record in records.items()
            },
            expected_requests=expected_requests,
        )
    entailer = entailer or default_entailer()
    interruptions: dict[str, str] = {}

    def finalize_batch(
        batch: Sequence[DriftInstance], execution: ProviderTaskExecution
    ) -> None:
        aliases = [f"drift_{900000 + index:06d}" for index in range(len(batch))]
        alias_rows = dict(zip(aliases, batch, strict=True))
        batch_records: list[EvaluationRecord] = []
        if system_id == "agent":
            if any(
                log.alias not in alias_rows or log.hunt not in AGENT_HUNTS
                for log in execution.tool_logs
            ):
                raise ValueError("agent execution contains an unconsumed tool log")
            envelope = CodexBatchEnvelope.model_validate_json(execution.final_message)
            validate_agent_envelope(envelope, aliases)
            by_alias = {result.alias: result for result in envelope.results}
            usage_recorded = execution.parsed.usage is not None
            allocations = allocate_tokens(
                execution.parsed.usage.total_tokens if usage_recorded else 0,
                len(batch) * len(AGENT_HUNTS),
            )
            for row_index, (alias, row) in enumerate(alias_rows.items()):
                with tempfile.TemporaryDirectory(
                    prefix="m4-config3-control-verify-"
                ) as temp:
                    tools = _tool_layer(
                        sources[row.instance_id], Path(temp), regulation_search
                    )
                    start = row_index * len(AGENT_HUNTS)
                    outcome = finalize_agent_case(
                        by_alias[alias],
                        clause=row.regulation_clause,
                        program_scope=Path(row.provenance.base_program).stem,
                        instance_id=row.instance_id,
                        logs=[log for log in execution.tool_logs if log.alias == alias],
                        tools=tools,
                        budget=AGENT_BUDGET,
                        entailer=entailer,
                        token_counts=allocations[start : start + len(AGENT_HUNTS)],
                        token_counts_recorded=usage_recorded,
                        min_successful_observations=MIN_AGENT_ABSTENTION_OBSERVATIONS,
                        model_id=MODEL_ID,
                    )
                batch_records.append(
                    record_outcome(
                        row,
                        outcome,
                        system_id=system_id,
                        source_sha256=sources[row.instance_id].source_sha256,
                        key=row_keys[row.instance_id],
                    )
                )
        else:
            if execution.tool_logs:
                raise ValueError("baseline execution contains unauthorized tool logs")
            envelope = CodexBaselineEnvelope.model_validate_json(
                execution.final_message
            )
            missing = validate_baseline_envelope(
                envelope,
                aliases,
                system_id=system_id,
                retrieved_counts={
                    alias: len(
                        contexts[row.instance_id]
                        .model_dump(mode="json")
                        .get("retrieved_clauses", [])
                    )
                    for alias, row in alias_rows.items()
                },
            )
            by_alias = {result.alias: result for result in envelope.results}
            usage_recorded = execution.parsed.usage is not None
            allocations = (
                allocate_tokens(
                    execution.parsed.usage.total_tokens if usage_recorded else 0,
                    len(by_alias),
                )
                if by_alias
                else []
            )
            returned = [alias for alias in aliases if alias in by_alias]
            for token_count, alias in zip(allocations, returned, strict=True):
                row = alias_rows[alias]
                submitted = by_alias[alias]
                context = _baseline_context(
                    system_id, contexts[row.instance_id].model_dump(mode="json")
                )
                clause = row.regulation_clause
                binding_error = None
                if submitted.response.kind == "finding":
                    try:
                        clause = select_baseline_clause(
                            system_id, submitted.clause_index, context
                        )
                    except (TypeError, ValueError) as exc:
                        binding_error = str(exc)
                response = bind_submitted_response(
                    submitted.response,
                    instance_id=row.instance_id,
                    clause=clause,
                    token_count=token_count,
                    token_count_recorded=usage_recorded,
                    prebinding_error=binding_error,
                )
                with tempfile.TemporaryDirectory(
                    prefix="m4-config3-control-verify-"
                ) as temp:
                    tools = _tool_layer(
                        sources[row.instance_id], Path(temp), regulation_search
                    )
                    record = single_shot_record(
                        row,
                        system_id=system_id,
                        source_sha256=sources[row.instance_id].source_sha256,
                        key=row_keys[row.instance_id],
                        context=context,
                        tools=tools,
                        model_factory=lambda response=response: _ReplayDecisionModel(
                            response, model_id=MODEL_ID
                        ),
                        entailer=entailer,
                    )
                batch_records.append(record)
            for alias in missing:
                row = alias_rows[alias]
                interruptions[row.instance_id] = "provider omitted required alias"
        for record in batch_records:
            key = row_keys[record.instance_id]
            prior = records.get(key)
            if prior is not None and prior != record:
                raise RuntimeError(f"refusing to replace completed record {key}")
            if prior is None:
                _write_record_sidecar(
                    sidecar_dir / f"{key}.json",
                    record,
                    execution=execution,
                    raw_bundle_key=row_to_batch_key[record.instance_id],
                )
                records[key] = record
            interruptions.pop(record.instance_id, None)

    def execute(batch: Sequence[DriftInstance]) -> CodexTaskExecution:
        if selected_execution is None:
            raise RuntimeError(
                "collaboration_subagent results must be ingested and sealed externally"
            )
        batch_key = batch_keys[batch[0].instance_id]
        prompt, schema, task_sources = request_parts[batch_key]
        return selected_execution(
            prompt=prompt,
            schema=schema,
            sources=task_sources,
            support_root=support_root,
            distro=distro,
            codex_binary=codex_binary,
            model_id=MODEL_ID,
            reasoning_effort=REASONING_EFFORT,
            timeout_s=_expected_budget(system_id).wall_clock_timeout_s,
            runtime_source_sha256=freeze.runtime_source_sha256,
            authentication_identity_sha256=freeze.chatgpt_account_sha256,
            authorized_hunts=authorized_hunts,
        )

    pending_batches: list[list[DriftInstance]] = []
    for batch in batches:
        if all(row_keys[row.instance_id] in records for row in batch):
            continue
        batch_key = batch_keys[batch[0].instance_id]
        bundle = load_execution_bundle(
            artifact_dir=artifact_dir,
            key=batch_key,
            expected_request_sha256=expected_requests[batch_key],
        )
        if bundle is None:
            pending_batches.append(batch)
        else:
            try:
                staged = staged_tasks.get(batch_key)
                if staged is not None:
                    validate_staged_collaboration_execution(
                        bundle,
                        staged=staged,
                        staging_base=staging_base,
                    )
                finalize_batch(batch, bundle)
            except Exception as exc:  # noqa: BLE001
                detail = f"finalization {type(exc).__name__}: {exc}"
                for row in batch:
                    if row_keys[row.instance_id] not in records:
                        interruptions[row.instance_id] = detail

    progress_path = artifact_dir / "progress.json"
    records_path = artifact_dir / f"{system_id}.jsonl"
    _write_progress(
        path=progress_path,
        freeze=freeze,
        system_id=system_id,
        mode=mode,
        rows=rows,
        records=records,
        row_keys=row_keys,
        interruptions=interruptions,
    )
    if collaboration:
        _write_canonical_records(records_path, records, seal.row_order)
        progress = _write_progress(
            path=progress_path,
            freeze=freeze,
            system_id=system_id,
            mode=mode,
            rows=rows,
            records=records,
            row_keys=row_keys,
            interruptions=interruptions,
        )
        if mode == "smoke":
            refresh_smoke_readiness(output_dir=Path(output_dir), freeze=freeze)
        return (
            [records[key] for key in seal.row_run_keys if key in records],
            progress,
        )
    for batch, execution_result, error in bounded_provider_map(
        pending_batches, execute, max_workers=max_workers
    ):
        if error is not None or execution_result is None:
            detail = f"{type(error).__name__}: {error}" if error else "unknown"
            for row in batch:
                interruptions[row.instance_id] = detail
        else:
            batch_key = batch_keys[batch[0].instance_id]
            try:
                _persist_immutable_bundle(
                    execution_result,
                    artifact_dir=artifact_dir,
                    key=batch_key,
                    expected_request_sha256=expected_requests[batch_key],
                )
                finalize_batch(batch, execution_result)
            except Exception as exc:  # noqa: BLE001
                detail = f"finalization {type(exc).__name__}: {exc}"
                for row in batch:
                    if row_keys[row.instance_id] not in records:
                        interruptions[row.instance_id] = detail
        _write_canonical_records(records_path, records, seal.row_order)
        progress = _write_progress(
            path=progress_path,
            freeze=freeze,
            system_id=system_id,
            mode=mode,
            rows=rows,
            records=records,
            row_keys=row_keys,
            interruptions=interruptions,
        )
        print(
            json.dumps(
                {
                    "system": system_id,
                    "mode": mode,
                    "completed": len(records),
                    "total": len(rows),
                    "pending": len(progress.pending_instance_ids),
                    "interruptions": len(interruptions),
                }
            ),
            flush=True,
        )
    _write_canonical_records(records_path, records, seal.row_order)
    progress = _write_progress(
        path=progress_path,
        freeze=freeze,
        system_id=system_id,
        mode=mode,
        rows=rows,
        records=records,
        row_keys=row_keys,
        interruptions=interruptions,
    )
    ordered = sorted(
        records.values(), key=lambda record: seal.row_order.index(record.instance_id)
    )
    if canonical_sha256(freeze) != freeze_hash:
        raise RuntimeError("configuration-3 freeze changed during control execution")
    if mode == "smoke":
        refresh_smoke_readiness(output_dir=Path(output_dir), freeze=freeze)
    return ordered, progress
