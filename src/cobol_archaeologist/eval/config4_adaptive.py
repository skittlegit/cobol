"""Provider-free replay and readiness scoring for configuration-4 adaptive dev.

This module is deliberately a consumer of the immutable configuration-4
train/dev preparation artifacts.  It never invokes a provider or stages a new
task.  A sealed collaboration capture is replayed through the existing
configuration-3 host finalizer, while request, staging, capture, and record
identities are checked before any score is reported.

The readiness artifact is engineering-only.  In particular, the roster is
the complete dev split and a partial/failed run cannot silently turn into a
smaller evaluation denominator.
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.eval.collaboration_staging import (
    StagedCollaborationTask,
    collaboration_tool_command,
    load_staging_manifest,
)
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationGroupIdentity,
    CollaborationSubagentExecutionV2,
    CollaborationSubagentRequest,
    load_collaboration_bundle,
)
from cobol_archaeologist.eval.config3_live import (
    CodexAdaptiveEnvelope,
    _load_record_sidecars,
    _replay_adaptive_record,
    _write_record_sidecar,
    validate_staged_collaboration_execution,
)
from cobol_archaeologist.eval.config4_prepare import (
    FREEZE_NAME,
    GROUP_ID,
    INDEX_NAME,
    REQUEST_DIRECTORY_NAME,
    SOURCE_ALIAS,
    STAGING_DIRECTORY_NAME,
    Config4DevFreeze,
    Config4DevPreparation,
    Config4RequestPin,
    canonical_sha256,
    load_train_dev_rows,
)
from cobol_archaeologist.eval.materialize import MaterializedSource, materialize
from cobol_archaeologist.eval.metrics import detection
from cobol_archaeologist.eval.phase5_headline import _balanced_accuracy_structured
from cobol_archaeologist.eval.schemas import EvaluationRecord
from cobol_archaeologist.model.verify import Entailer, LexicalEntailer

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXPECTED_DEV_ROWS = 102
RECORD_DIRECTORY_NAME = "adaptive-dev-records-v1"
PROGRESS_NAME = "adaptive-dev-progress-v1.json"
READINESS_NAME = "adaptive-dev-readiness-v1.json"
ZERO_HASH = "0" * 64


class Config4ReplayFailure(BaseModel):
    """One durable explanation for a host or provider-side replay failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["infrastructure", "contract"]
    instance_id: str
    run_key: str | None = None
    reason: str = Field(min_length=1)


class Config4AdaptiveProgress(BaseModel):
    """Mutable, hash-bound progress for a resumable dev replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-adaptive-dev-progress-v1"] = (
        "configuration-4-adaptive-dev-progress-v1"
    )
    configuration: Literal[4] = 4
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_row_count: int = Field(ge=0)
    completed_run_keys: tuple[str, ...] = ()
    pending_instance_ids: tuple[str, ...] = ()
    infrastructure_failures: dict[str, Config4ReplayFailure] = Field(
        default_factory=dict
    )
    contract_rejections: dict[str, Config4ReplayFailure] = Field(default_factory=dict)


class Config4AdaptiveReadiness(BaseModel):
    """Engineering gate for a complete configuration-4 adaptive dev trial."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-adaptive-dev-readiness-v1"] = (
        "configuration-4-adaptive-dev-readiness-v1"
    )
    configuration: Literal[4] = 4
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_row_count: int = Field(ge=0)
    completed_rows: int = Field(ge=0)
    pending_instance_ids: tuple[str, ...] = ()
    infrastructure_failures: dict[str, Config4ReplayFailure] = Field(
        default_factory=dict
    )
    contract_rejections: dict[str, Config4ReplayFailure] = Field(default_factory=dict)
    unverified_emissions: int = Field(ge=0)
    full_coverage_f1: float = Field(ge=0.0, le=1.0)
    balanced_accuracy: float = Field(ge=0.0, le=1.0)
    answer_rate: float = Field(ge=0.0, le=1.0)
    answered_accuracy: float = Field(ge=0.0, le=1.0)
    gates: dict[str, bool]
    all_gates_pass: bool
    status: Literal["IN_PROGRESS", "VALID", "NOT_EVALUABLE"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_replace(path: Path, rendered: str) -> None:
    """Replace a mutable progress artifact atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _write_mutable(path: Path, model: BaseModel) -> None:
    _atomic_replace(path, model.model_dump_json(indent=2))


def _inside(root: Path, path: Path) -> Path:
    resolved_root = Path(root).resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"configuration-4 artifact leaves root: {path}")
    return resolved


def _failure(
    *,
    kind: Literal["infrastructure", "contract"],
    instance_id: str,
    reason: str,
    run_key: str | None = None,
) -> Config4ReplayFailure:
    return Config4ReplayFailure(
        kind=kind,
        instance_id=instance_id,
        run_key=run_key,
        reason=reason,
    )


def _failure_key(instance_id: str, suffix: str) -> str:
    return f"{instance_id}:{suffix}"


def _load_freeze_and_preparation(
    *, output_dir: Path
) -> tuple[Config4DevFreeze | None, Config4DevPreparation | None, dict[str, str]]:
    """Load immutable preparation artifacts and return host-side failures."""

    failures: dict[str, str] = {}
    freeze: Config4DevFreeze | None = None
    preparation: Config4DevPreparation | None = None
    freeze_path = output_dir / FREEZE_NAME
    index_path = output_dir / INDEX_NAME
    try:
        freeze = Config4DevFreeze.model_validate_json(
            freeze_path.read_text(encoding="utf-8")
        )
    except Exception as exc:  # noqa: BLE001 - persisted artifact is untrusted input
        failures["__freeze__"] = f"invalid configuration-4 freeze: {type(exc).__name__}: {exc}"
    try:
        preparation = Config4DevPreparation.model_validate_json(
            index_path.read_text(encoding="utf-8")
        )
    except Exception as exc:  # noqa: BLE001 - persisted artifact is untrusted input
        failures["__preparation__"] = (
            "invalid configuration-4 request preparation: "
            f"{type(exc).__name__}: {exc}"
        )
    if freeze is not None:
        expected_freeze = canonical_sha256(freeze)
        if not freeze_path.is_file():
            failures["__freeze_sha256__"] = "configuration-4 freeze artifact is absent"
        elif freeze_path.read_bytes() != freeze.model_dump_json(indent=2).encode(
            "utf-8"
        ):
            failures["__freeze_bytes__"] = (
                "configuration-4 freeze bytes are not the canonical frozen model"
            )
        if preparation is not None:
            if index_path.is_file() and index_path.read_bytes() != preparation.model_dump_json(
                indent=2
            ).encode("utf-8"):
                failures["__preparation_bytes__"] = (
                    "request preparation bytes are not the canonical frozen model"
                )
            if preparation.freeze_sha256 != expected_freeze:
                failures["__freeze_chain__"] = (
                    "request preparation is bound to a different freeze"
                )
            if not freeze_path.is_file() or preparation.freeze_artifact_sha256 != _sha(
                freeze_path
            ):
                failures["__freeze_artifact__"] = (
                    "request preparation freeze artifact hash differs"
                )
    if freeze is not None and freeze.selection != "dev":
        failures["__selection__"] = "adaptive readiness requires the dev-only selection"
    if preparation is not None and preparation.status != "PROVIDER_FREE_READY_NON_HEADLINE":
        failures["__preparation_status__"] = "request preparation is not provider-free dev readiness"
    return freeze, preparation, failures


def _request_path(*, root: Path, output_dir: Path, pin: Config4RequestPin) -> Path:
    path = _inside(root, root / pin.request_path)
    expected = (output_dir / REQUEST_DIRECTORY_NAME / f"{pin.run_key}.json").resolve()
    if path != expected:
        raise ValueError("request pin points outside this output directory")
    return path


def _staging_path(*, root: Path, output_dir: Path, pin: Config4RequestPin) -> Path:
    path = _inside(root, root / pin.staging_path)
    expected = (output_dir / STAGING_DIRECTORY_NAME / pin.run_key).resolve()
    if path != expected:
        raise ValueError("staging pin points outside this output directory")
    return path


def _load_request(
    *,
    root: Path,
    output_dir: Path,
    pin: Config4RequestPin,
    freeze: Config4DevFreeze,
    task_count: int,
) -> CollaborationSubagentRequest:
    path = _request_path(root=root, output_dir=output_dir, pin=pin)
    if not path.is_file():
        raise FileNotFoundError(f"request artifact is missing: {path}")
    if _sha(path) != pin.request_artifact_sha256:
        raise ValueError("request artifact bytes differ from the pinned hash")
    rendered = path.read_bytes()
    request = CollaborationSubagentRequest.model_validate_json(
        rendered.decode("utf-8")
    )
    if rendered != request.model_dump_json(indent=2).encode("utf-8"):
        raise ValueError("request artifact bytes are not canonical")
    if request.run_key != pin.run_key or request.request_sha256 != pin.request_sha256:
        raise ValueError("request identity differs from its preparation pin")
    if request.source_sha256 != {SOURCE_ALIAS: pin.source_sha256}:
        raise ValueError("request source identity differs from its preparation pin")
    if request.runtime_source_sha256 != freeze.runtime_source_sha256:
        raise ValueError("request runtime identity differs from its freeze")
    expected_group = CollaborationGroupIdentity(
        group_id=GROUP_ID,
        mode="concurrent" if task_count > 1 else "sequential",
        ordinal=pin.ordinal,
        size=task_count,
    )
    if request.group != expected_group:
        raise ValueError("request group identity differs from its preparation order")
    if (
        request.schema_version != "configuration-3-collaboration-request-v2"
        or request.visible_cases != 1
        or request.authorized_hunts != ("adaptive",)
        or request.prior_case_context_included
    ):
        raise ValueError("request is not a one-case adaptive Luna/max task")
    return request


def _load_staged(
    *,
    root: Path,
    output_dir: Path,
    pin: Config4RequestPin,
) -> StagedCollaborationTask:
    task_root = _staging_path(root=root, output_dir=output_dir, pin=pin)
    staging_base = task_root.parent
    manifest_path = task_root / "staging-manifest.json"
    if not manifest_path.is_file() or _sha(manifest_path) != pin.staging_manifest_sha256:
        raise ValueError("staging manifest bytes differ from the preparation pin")
    manifest = load_staging_manifest(
        staging_base=staging_base,
        run_key=pin.run_key,
        expected_staging_sha256=pin.staging_sha256,
    )
    if manifest.staging_sha256 != pin.staging_sha256:
        raise ValueError("staging manifest identity differs from the preparation pin")
    return StagedCollaborationTask(
        task_root=task_root,
        run_key=pin.run_key,
        staging_sha256=pin.staging_sha256,
        tool_command=collaboration_tool_command(
            staging_base=staging_base,
            run_key=pin.run_key,
            staging_sha256=pin.staging_sha256,
        ),
    )


def _materialized_source(
    row: Any,
    *,
    programs_root: Path | None,
    expected_sha256: str,
) -> MaterializedSource:
    source = (
        materialize(row)
        if programs_root is None
        else materialize(row, programs_root=programs_root)
    )
    if source.source_sha256 != expected_sha256:
        raise ValueError("materialized source differs from the preparation pin")
    return source


def _load_existing_records(
    directory: Path,
) -> tuple[dict[str, EvaluationRecord], dict[str, Any], str | None]:
    try:
        records, markers = _load_record_sidecars(directory)
    except Exception as exc:  # noqa: BLE001 - record artifacts are untrusted input
        return {}, {}, f"invalid adaptive record sidecar set: {type(exc).__name__}: {exc}"
    return records, markers, None


def _raw_chain_matches(
    *,
    record: EvaluationRecord,
    marker: Any,
    execution: Any,
    run_key: str,
    request_sha256: str,
) -> bool:
    return (
        record.run_key == run_key
        and marker.run_key == run_key
        and marker.raw_bundle_key == run_key
        and marker.raw_request_sha256 == request_sha256
        and execution.request_sha256 == request_sha256
        and marker.raw_execution_sha256 == canonical_sha256(execution)
    )


def _unverified_emissions(records: Sequence[EvaluationRecord]) -> int:
    return sum(
        record.prediction is not None
        and (record.verification is None or not record.verification.verified)
        for record in records
    )


def score_config4_adaptive_readiness(
    *,
    records: Sequence[EvaluationRecord],
    expected_row_count: int,
    freeze_sha256: str,
    pending_instance_ids: Sequence[str] = (),
    infrastructure_failures: Mapping[str, Config4ReplayFailure] = {},
    contract_rejections: Mapping[str, Config4ReplayFailure] = {},
) -> Config4AdaptiveReadiness:
    """Score records and apply every non-headline adaptive-dev gate."""

    if expected_row_count < 0:
        raise ValueError("expected dev row count cannot be negative")
    unique_ids = {record.instance_id for record in records}
    if len(unique_ids) != len(records):
        raise ValueError("adaptive dev records contain duplicate instance IDs")
    metrics = detection(records)
    balanced = _balanced_accuracy_structured(records)
    unverified = _unverified_emissions(records)
    pending = tuple(sorted(set(pending_instance_ids)))
    infrastructure = dict(sorted(infrastructure_failures.items()))
    contracts = dict(sorted(contract_rejections.items()))
    for record in records:
        if record.infrastructure_error:
            key = _failure_key(record.instance_id, "record_infrastructure")
            infrastructure[key] = _failure(
                kind="infrastructure",
                instance_id=record.instance_id,
                run_key=record.run_key,
                reason=record.infrastructure_error,
            )
    gates = {
        "complete_102_row_dev_trial": len(records) == expected_row_count,
        "zero_infrastructure_failures": not infrastructure,
        "zero_contract_rejections": not contracts,
        "zero_unverified_emissions": unverified == 0,
        "answer_rate_at_least_0.60": metrics["answer_rate"] >= 0.60,
        "full_coverage_f1_at_least_0.70": metrics["f1"] >= 0.70,
        "balanced_accuracy_at_least_0.65": balanced >= 0.65,
        "answered_accuracy_at_least_0.80": metrics["answered_accuracy"] >= 0.80,
    }
    all_gates_pass = all(gates.values())
    if all_gates_pass:
        status: Literal["IN_PROGRESS", "VALID", "NOT_EVALUABLE"] = "VALID"
    elif (
        (pending or len(records) < expected_row_count)
        and not infrastructure
        and not contracts
    ):
        status = "IN_PROGRESS"
    else:
        status = "NOT_EVALUABLE"
    return Config4AdaptiveReadiness(
        freeze_sha256=freeze_sha256,
        expected_row_count=expected_row_count,
        completed_rows=len(records),
        pending_instance_ids=pending,
        infrastructure_failures=infrastructure,
        contract_rejections=contracts,
        unverified_emissions=unverified,
        full_coverage_f1=metrics["f1"],
        balanced_accuracy=balanced,
        answer_rate=metrics["answer_rate"],
        answered_accuracy=metrics["answered_accuracy"],
        gates=gates,
        all_gates_pass=all_gates_pass,
        status=status,
    )


def _write_progress_and_readiness(
    *,
    output_dir: Path,
    progress: Config4AdaptiveProgress,
    readiness: Config4AdaptiveReadiness,
) -> None:
    _write_mutable(output_dir / PROGRESS_NAME, progress)
    _write_mutable(output_dir / READINESS_NAME, readiness)


def replay_config4_adaptive_dev(
    *,
    root: Path = ROOT,
    output_dir: Path,
    capture_dir: Path | None = None,
    expected_row_count: int = DEFAULT_EXPECTED_DEV_ROWS,
    programs_root: Path | None = None,
    entailer: Entailer | None = None,
) -> Config4AdaptiveReadiness:
    """Replay sealed train/dev captures without running a provider.

    ``capture_dir`` defaults to ``output_dir`` because collaboration sealing
    writes ``raw/<run-key>`` beside the train/dev request preparation.  It is
    separately configurable for a coordinator that copies immutable captures
    into another train/dev lineage directory.
    """

    root = Path(root).resolve()
    output_dir = _inside(root, Path(output_dir))
    if "m4-config3" in {part.lower() for part in output_dir.parts}:
        raise ValueError("configuration-4 replay cannot write or read config3 artifacts")
    capture_dir = output_dir if capture_dir is None else _inside(root, Path(capture_dir))
    if expected_row_count < 0:
        raise ValueError("expected dev row count cannot be negative")
    entailer = entailer or LexicalEntailer()

    infrastructure: dict[str, Config4ReplayFailure] = {}
    contracts: dict[str, Config4ReplayFailure] = {}
    pending: list[str] = []
    records_dir = output_dir / RECORD_DIRECTORY_NAME
    records, markers, record_error = _load_existing_records(records_dir)
    if record_error is not None:
        infrastructure["__records__"] = _failure(
            kind="infrastructure", instance_id="__records__", reason=record_error
        )
        records = {}
        markers = {}

    try:
        rows_with_split = load_train_dev_rows(root=root, selection="dev")
    except Exception as exc:  # noqa: BLE001 - dev roster is host input
        rows_with_split = ()
        infrastructure["__dev_roster__"] = _failure(
            kind="infrastructure",
            instance_id="__dev_roster__",
            reason=f"unable to load dev roster: {type(exc).__name__}: {exc}",
        )
    rows = {row.instance_id: (row, split) for row, split in rows_with_split}
    if len(rows) != expected_row_count:
        infrastructure["__dev_roster_count__"] = _failure(
            kind="infrastructure",
            instance_id="__dev_roster__",
            reason=(
                f"expected {expected_row_count} dev rows, observed {len(rows)}; "
                "the complete dev gate cannot use a smaller denominator"
            ),
        )

    freeze, preparation, artifact_failures = _load_freeze_and_preparation(
        output_dir=output_dir
    )
    for key, reason in artifact_failures.items():
        infrastructure[key] = _failure(
            kind="infrastructure", instance_id=key, reason=reason
        )
    freeze_hash = canonical_sha256(freeze) if freeze is not None else ZERO_HASH
    pins: dict[str, Config4RequestPin] = {}
    task_count = preparation.task_count if preparation is not None else 0
    if preparation is not None:
        for pin in preparation.request_order:
            if pin.instance_id in pins:
                infrastructure[_failure_key(pin.instance_id, "duplicate_pin")] = _failure(
                    kind="infrastructure",
                    instance_id=pin.instance_id,
                    run_key=pin.run_key,
                    reason="request preparation contains duplicate instance pins",
                )
            pins[pin.instance_id] = pin
        if task_count != len(pins) or len(
            {pin.run_key for pin in preparation.request_order}
        ) != len(preparation.request_order):
            infrastructure["__preparation_count__"] = _failure(
                kind="infrastructure",
                instance_id="__preparation__",
                reason="request preparation contains duplicate run identities",
            )
    known_run_keys = {pin.run_key for pin in pins.values()}
    for run_key in sorted(set(records) - known_run_keys):
        infrastructure[_failure_key(run_key, "stale_record")] = _failure(
            kind="infrastructure",
            instance_id="__records__",
            run_key=run_key,
            reason="record sidecar is not part of the current immutable request order",
        )
    if freeze is not None:
        frozen_ids = {item.instance_id for item in freeze.selected_rows}
        frozen_by_id = {item.instance_id: item for item in freeze.selected_rows}
        for instance_id in sorted(set(rows) - frozen_ids):
            infrastructure[_failure_key(instance_id, "not_selected")] = _failure(
                kind="infrastructure",
                instance_id=instance_id,
                reason="dev row is absent from the immutable configuration-4 freeze",
            )
        for instance_id in sorted(frozen_ids - set(rows)):
            infrastructure[_failure_key(instance_id, "not_dev")]= _failure(
                kind="infrastructure",
                instance_id=instance_id,
                reason="freeze selected a row outside the complete dev roster",
            )
    for instance_id in sorted(set(rows) - set(pins)):
        infrastructure[_failure_key(instance_id, "not_prepared")] = _failure(
            kind="infrastructure",
            instance_id=instance_id,
            reason="dev row has no immutable provider-free request preparation",
        )
    for instance_id, pin in sorted(pins.items()):
        if instance_id not in rows:
            infrastructure[_failure_key(instance_id, "unexpected_pin")] = _failure(
                kind="infrastructure",
                instance_id=instance_id,
                run_key=pin.run_key,
                reason="request preparation contains a non-dev row",
            )
        elif pin.source_split != rows[instance_id][1]:
            infrastructure[_failure_key(instance_id, "split_mismatch")] = _failure(
                kind="infrastructure",
                instance_id=instance_id,
                run_key=pin.run_key,
                reason="request pin split differs from the dev roster",
            )
        if freeze is not None and instance_id in frozen_by_id:
            frozen = frozen_by_id[instance_id]
            if (
                pin.source_sha256 != frozen.source_sha256
                or pin.source_split != frozen.source_split
            ):
                infrastructure[_failure_key(instance_id, "freeze_mismatch")] = _failure(
                    kind="infrastructure",
                    instance_id=instance_id,
                    run_key=pin.run_key,
                    reason="request pin differs from the immutable freeze row identity",
                )

    completed: dict[str, EvaluationRecord] = {}
    # Existing records are only eligible if their corresponding pin/raw chain
    # is still present.  A missing capture is pending only when no record was
    # previously sealed for that run key.
    for instance_id in sorted(rows):
        row, _split = rows[instance_id]
        pin = pins.get(instance_id)
        if pin is None:
            continue
        request: CollaborationSubagentRequest | None = None
        staged: StagedCollaborationTask | None = None
        try:
            if freeze is None or preparation is None:
                raise ValueError("freeze/preparation artifacts are unavailable")
            request = _load_request(
                root=root,
                output_dir=output_dir,
                pin=pin,
                freeze=freeze,
                task_count=task_count,
            )
            staged = _load_staged(root=root, output_dir=output_dir, pin=pin)
        except Exception as exc:  # noqa: BLE001 - host artifacts are untrusted input
            infrastructure[_failure_key(instance_id, "host_artifact")] = _failure(
                kind="infrastructure",
                instance_id=instance_id,
                run_key=pin.run_key,
                reason=f"invalid immutable request/staging: {type(exc).__name__}: {exc}",
            )
            continue

        existing = records.get(pin.run_key)
        if existing is not None:
            try:
                if existing.instance_id != instance_id or existing.source_sha256 != pin.source_sha256:
                    raise ValueError("existing record differs from the request pin")
                if pin.run_key not in markers:
                    raise ValueError("existing record has no sidecar marker")
                execution = load_collaboration_bundle(
                    artifact_dir=capture_dir,
                    key=pin.run_key,
                    expected_request_sha256=request.request_sha256,
                )
                if execution is None:
                    raise ValueError("existing record has no immutable raw capture")
                if execution.request != request:
                    raise ValueError(
                        "existing capture request differs from the request artifact"
                    )
                if not _raw_chain_matches(
                    record=existing,
                    marker=markers[pin.run_key],
                    execution=execution,
                    run_key=pin.run_key,
                    request_sha256=request.request_sha256,
                ):
                    raise ValueError("existing record/raw execution chain differs")
                if not isinstance(execution, CollaborationSubagentExecutionV2):
                    raise TypeError("existing record raw capture is not collaboration v2")
                validate_staged_collaboration_execution(
                    execution, staged=staged, staging_base=staged.task_root.parent
                )
                CodexAdaptiveEnvelope.model_validate_json(execution.final_message)
                completed[pin.run_key] = existing
            except Exception as exc:  # noqa: BLE001 - immutable chain is untrusted input
                infrastructure[_failure_key(instance_id, "record_chain")] = _failure(
                    kind="infrastructure",
                    instance_id=instance_id,
                    run_key=pin.run_key,
                    reason=f"invalid immutable record chain: {type(exc).__name__}: {exc}",
                )
            continue

        try:
            execution = load_collaboration_bundle(
                artifact_dir=capture_dir,
                key=pin.run_key,
                expected_request_sha256=request.request_sha256,
            )
        except Exception as exc:  # noqa: BLE001 - capture bytes are untrusted input
            contracts[_failure_key(instance_id, "capture_bundle")] = _failure(
                kind="contract",
                instance_id=instance_id,
                run_key=pin.run_key,
                reason=(
                    "invalid immutable capture bundle: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            continue
        if execution is None:
            pending.append(instance_id)
            continue
        try:
            if not isinstance(execution, CollaborationSubagentExecutionV2):
                raise TypeError("sealed capture is not collaboration execution-v2")
            if execution.request != request:
                raise ValueError("sealed capture request differs from the immutable request")
            validate_staged_collaboration_execution(
                execution, staged=staged, staging_base=staged.task_root.parent
            )
            CodexAdaptiveEnvelope.model_validate_json(execution.final_message)
            try:
                source = _materialized_source(
                    row,
                    programs_root=programs_root,
                    expected_sha256=pin.source_sha256,
                )
            except Exception as exc:  # noqa: BLE001 - source is host input
                infrastructure[_failure_key(instance_id, "source")] = _failure(
                    kind="infrastructure",
                    instance_id=instance_id,
                    run_key=pin.run_key,
                    reason=(
                        "materialized source does not match the frozen request: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
                continue
            record = _replay_adaptive_record(
                row,
                source=source,
                execution=execution,
                key=pin.run_key,
                entailer=entailer,
            )
            _write_record_sidecar(
                records_dir / f"{pin.run_key}.json",
                record,
                execution=execution,
                raw_bundle_key=pin.run_key,
            )
            completed[pin.run_key] = record
        except (TypeError, ValueError, KeyError) as exc:
            contracts[_failure_key(instance_id, "capture")] = _failure(
                kind="contract",
                instance_id=instance_id,
                run_key=pin.run_key,
                reason=f"capture failed strict replay validation: {type(exc).__name__}: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - finalizer/verifier must fail closed
            contracts[_failure_key(instance_id, "finalizer")] = _failure(
                kind="contract",
                instance_id=instance_id,
                run_key=pin.run_key,
                reason=f"host finalizer rejected capture: {type(exc).__name__}: {exc}",
            )

    records_by_id = {record.instance_id: record for record in completed.values()}
    readiness = score_config4_adaptive_readiness(
        records=tuple(records_by_id.values()),
        expected_row_count=expected_row_count,
        freeze_sha256=freeze_hash,
        pending_instance_ids=pending,
        infrastructure_failures=infrastructure,
        contract_rejections=contracts,
    )
    progress = Config4AdaptiveProgress(
        freeze_sha256=freeze_hash,
        expected_row_count=expected_row_count,
        completed_run_keys=tuple(sorted(completed)),
        pending_instance_ids=readiness.pending_instance_ids,
        infrastructure_failures=infrastructure,
        contract_rejections=contracts,
    )
    _write_progress_and_readiness(
        output_dir=output_dir, progress=progress, readiness=readiness
    )
    return readiness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay provider-sealed configuration-4 adaptive dev captures"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--expected-dev-rows", type=int, default=DEFAULT_EXPECTED_DEV_ROWS)
    parser.add_argument("--programs-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    readiness = replay_config4_adaptive_dev(
        root=args.root,
        output_dir=args.output_dir,
        capture_dir=args.capture_dir,
        expected_row_count=args.expected_dev_rows,
        programs_root=args.programs_root,
    )
    print(readiness.model_dump_json(indent=2))
    return 0 if readiness.status == "VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())
