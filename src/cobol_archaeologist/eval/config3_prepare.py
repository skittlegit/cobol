"""Deterministic, provider-free preparation of configuration-3 smoke tasks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationSubagentRequest,
)
from cobol_archaeologist.eval.config3_controls import run_config3_control
from cobol_archaeologist.eval.config3_live import (
    COLLABORATION_FREEZE_PATH,
    CONFIG3_SYSTEMS,
    OUTPUT_DIR,
    ROOT,
    Config3RunFreeze,
    _atomic_write,
    _load_split,
    build_config3_freeze,
    canonical_sha256,
    ensure_frozen_identity,
    run_config3_adaptive,
    seeded_dev_smoke,
)
from cobol_archaeologist.eval.run import repository_commit
from cobol_archaeologist.model.verify import LexicalEntailer
from cobol_archaeologist.schemas import DriftInstance

LEGACY_PLAN_PATH = OUTPUT_DIR / "collaboration-smoke-plan.json"
PLAN_PATH = OUTPUT_DIR / "collaboration-smoke-plan-v2.json"
COLLABORATION_OUTPUT_DIR = OUTPUT_DIR / "lineage-v4"
LEGACY_INDEX_NAME = "smoke-request-preparation.json"
INDEX_NAME = "smoke-request-preparation-v2.json"


class SmokePlanSystem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system_id: str
    batch_size: int = Field(ge=1)
    task_count: int = Field(ge=1)
    group_id: str
    group_mode: Literal["concurrent"]
    request_artifact_directory: str


class CollaborationSmokePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[
        "configuration-3-collaboration-smoke-plan-v1",
        "configuration-3-collaboration-smoke-plan-v2",
    ]
    status: Literal["REQUEST_IDENTITIES_PENDING_RUN_FREEZE"]
    provider: Literal["collaboration_subagent"]
    transport: Literal["collaboration_subagent"]
    authentication: Literal["in_product_orchestration"]
    model_id: Literal["gpt-5.6-luna"]
    reasoning_effort: Literal["max"]
    run_mode: Literal["smoke"]
    development_smoke_path: str
    development_smoke_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: Literal[14]
    hidden_test_rows: Literal[0]
    system_row_evaluations: Literal[84]
    task_count: Literal[37]
    max_concurrent_tasks: Literal[3]
    systems: tuple[SmokePlanSystem, ...]
    request_identity_rule: str
    execution_rule: str
    resume_rule: str
    release_gate: str

    @model_validator(mode="after")
    def _system_roster_is_exact(self) -> CollaborationSmokePlan:
        if tuple(item.system_id for item in self.systems) != CONFIG3_SYSTEMS:
            raise ValueError("collaboration smoke plan system order differs")
        if sum(item.task_count for item in self.systems) != self.task_count:
            raise ValueError("collaboration smoke plan task count differs")
        for item in self.systems:
            expected_group = f"config3:smoke:{item.system_id}"
            request_directory = (
                "requests-v3"
                if item.system_id in {"agent", "adaptive_agent"}
                else (
                    "requests-v2"
                    if self.schema_version
                    == "configuration-3-collaboration-smoke-plan-v2"
                    else "requests"
                )
            )
            expected_directory = (
                "data/eval/m4-config3/lineage-v4/smoke/"
                f"{item.system_id}/{request_directory}"
            )
            if (
                item.group_id != expected_group
                or item.request_artifact_directory != expected_directory
            ):
                raise ValueError(
                    f"{item.system_id} collaboration smoke path/group differs"
                )
        return self


class SmokeRequestPin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system_id: str
    group_id: str
    ordinal: int = Field(ge=1)
    visible_cases: int = Field(ge=1)
    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Config3SmokeRequestPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-3-smoke-request-preparation-v2"] = (
        "configuration-3-smoke-request-preparation-v2"
    )
    status: Literal["MODEL_PROMPTS_READY_TRANSCRIPT_PROTOCOL_PENDING"]
    provider_calls_performed: Literal[0]
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: Literal[14]
    system_row_evaluations: Literal[84]
    task_count: Literal[37]
    request_order: tuple[SmokeRequestPin, ...] = Field(min_length=37, max_length=37)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_collaboration_smoke_plan(
    *, root: Path = ROOT, plan_path: Path | None = None
) -> tuple[CollaborationSmokePlan, Path]:
    root = Path(root).resolve()
    path = (
        Path(plan_path).resolve()
        if plan_path is not None
        else root / PLAN_PATH.relative_to(ROOT)
    )
    plan = CollaborationSmokePlan.model_validate_json(path.read_text(encoding="utf-8"))
    development = (root / plan.development_smoke_path).resolve()
    if (
        not development.is_relative_to(root)
        or _sha(development) != plan.development_smoke_sha256
    ):
        raise RuntimeError("collaboration smoke plan development roster changed")
    return plan, path


def build_collaboration_smoke_freeze(
    *, root: Path = ROOT, plan_path: Path | None = None
) -> tuple[Config3RunFreeze, CollaborationSmokePlan, Path]:
    """Build only after finalized T6 validation; this function writes nothing."""

    root = Path(root).resolve()
    plan, resolved_plan = load_collaboration_smoke_plan(root=root, plan_path=plan_path)
    freeze = build_config3_freeze(
        repository_commit_value=repository_commit(root),
        transport="collaboration_subagent",
        max_workers=plan.max_concurrent_tasks,
        root=root,
    )
    if (
        freeze.provider != plan.provider
        or freeze.transport != plan.transport
        or freeze.authentication != plan.authentication
        or freeze.model_id != plan.model_id
        or freeze.reasoning_effort != plan.reasoning_effort
        or len(freeze.smoke_instance_ids) != plan.row_count
    ):
        raise RuntimeError("collaboration smoke plan differs from run freeze")
    for item in plan.systems:
        expected_tasks = (plan.row_count + item.batch_size - 1) // item.batch_size
        if (
            freeze.batch_sizes.get(item.system_id) != item.batch_size
            or expected_tasks != item.task_count
        ):
            raise RuntimeError(f"{item.system_id} task grouping differs from plan")
    return freeze, plan, resolved_plan


def _smoke_rows(freeze: Config3RunFreeze, *, root: Path) -> list[DriftInstance]:
    dev = _load_split(root / freeze.dev_split_path)
    train = _load_split(root / freeze.train_split_path)
    rows = seeded_dev_smoke(dev, fallback_rows=train, seed=freeze.smoke_seed)
    if tuple(row.instance_id for row in rows) != freeze.smoke_instance_ids:
        raise RuntimeError("selected smoke rows differ from run freeze")
    return rows


def write_smoke_request_preparation(
    *,
    freeze: Config3RunFreeze,
    plan: CollaborationSmokePlan,
    plan_path: Path,
    output_dir: Path,
    root: Path = ROOT,
) -> Config3SmokeRequestPreparation:
    """Validate all 37 typed requests before writing the readiness receipt."""

    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_relative_to(root):
        raise ValueError("configuration-3 output directory leaves the repository")
    freeze_path = output_dir / COLLABORATION_FREEZE_PATH.name
    if not freeze_path.is_file():
        raise RuntimeError("configuration-3 run freeze is missing")
    persisted = Config3RunFreeze.model_validate_json(
        freeze_path.read_text(encoding="utf-8")
    )
    if persisted != freeze:
        raise RuntimeError("persisted configuration-3 run freeze differs")
    pins: list[SmokeRequestPin] = []
    run_keys: set[str] = set()
    for item in plan.systems:
        request_dir = (root / item.request_artifact_directory).resolve()
        if not request_dir.is_relative_to(root):
            raise ValueError("collaboration request directory leaves the repository")
        request_paths = sorted(request_dir.glob("*.json"))
        if len(request_paths) != item.task_count:
            raise RuntimeError(f"{item.system_id} typed request roster is incomplete")
        requests = [
            (
                path,
                CollaborationSubagentRequest.model_validate_json(
                    path.read_text(encoding="utf-8")
                ),
            )
            for path in request_paths
        ]
        requests.sort(key=lambda value: value[1].group.ordinal)
        if (
            [request.group.ordinal for _, request in requests]
            != list(range(1, item.task_count + 1))
            or any(
                request.group.group_id != item.group_id
                or request.group.mode != item.group_mode
                or request.group.size != item.task_count
                or request.runtime_source_sha256 != freeze.runtime_source_sha256
                for _, request in requests
            )
            or sum(request.visible_cases for _, request in requests) != plan.row_count
        ):
            raise RuntimeError(f"{item.system_id} typed request grouping differs")
        for path, request in requests:
            if request.run_key in run_keys or path.stem != request.run_key:
                raise RuntimeError("collaboration smoke request key is not unique")
            run_keys.add(request.run_key)
            pins.append(
                SmokeRequestPin(
                    system_id=item.system_id,
                    group_id=item.group_id,
                    ordinal=request.group.ordinal,
                    visible_cases=request.visible_cases,
                    run_key=request.run_key,
                    request_sha256=request.request_sha256,
                    path=path.relative_to(root).as_posix(),
                    artifact_sha256=_sha(path),
                )
            )
    if len(pins) != plan.task_count:
        raise RuntimeError("collaboration smoke request count differs from plan")
    preparation = Config3SmokeRequestPreparation(
        status="MODEL_PROMPTS_READY_TRANSCRIPT_PROTOCOL_PENDING",
        provider_calls_performed=0,
        freeze_sha256=canonical_sha256(freeze),
        freeze_artifact_sha256=_sha(freeze_path),
        plan_sha256=_sha(plan_path),
        row_count=plan.row_count,
        system_row_evaluations=plan.system_row_evaluations,
        task_count=plan.task_count,
        request_order=tuple(pins),
    )
    index_path = output_dir / INDEX_NAME
    rendered = preparation.model_dump_json(indent=2)
    if index_path.exists():
        prior = Config3SmokeRequestPreparation.model_validate_json(
            index_path.read_text(encoding="utf-8")
        )
        if prior != preparation:
            raise RuntimeError("configuration-3 smoke preparation differs")
    else:
        _atomic_write(index_path, rendered)
    return preparation


def prepare_config3_collaboration_smoke(
    *,
    root: Path = ROOT,
    output_dir: Path = COLLABORATION_OUTPUT_DIR,
    plan_path: Path | None = None,
) -> Config3SmokeRequestPreparation:
    """Freeze and emit self-contained prompts without any provider/model call."""

    root = Path(root).resolve()
    if root != ROOT.resolve():
        raise ValueError("configuration-3 runners require the repository root")
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_relative_to(root):
        raise ValueError("configuration-3 output directory leaves the repository")
    freeze, plan, resolved_plan = build_collaboration_smoke_freeze(
        root=root, plan_path=plan_path
    )
    ensure_frozen_identity(output_dir / COLLABORATION_FREEZE_PATH.name, freeze)
    rows = _smoke_rows(freeze, root=root)
    entailer = LexicalEntailer()
    for system_id in CONFIG3_SYSTEMS:
        if system_id == "adaptive_agent":
            run_config3_adaptive(
                rows=rows,
                mode="smoke",
                freeze=freeze,
                output_dir=output_dir,
                max_workers=freeze.max_workers,
                transport="collaboration_subagent",
                entailer=entailer,
            )
        else:
            run_config3_control(
                system_id,
                rows=rows,
                mode="smoke",
                freeze=freeze,
                output_dir=output_dir,
                max_workers=freeze.max_workers,
                transport="collaboration_subagent",
                entailer=entailer,
            )
    return write_smoke_request_preparation(
        freeze=freeze,
        plan=plan,
        plan_path=resolved_plan,
        output_dir=output_dir,
        root=root,
    )
