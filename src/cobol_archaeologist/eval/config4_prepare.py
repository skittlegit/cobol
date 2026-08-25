"""Provider-free preparation of configuration-4 adaptive train/dev tasks.

Configuration 4 is a successor engineering lineage.  This module deliberately
does not run a provider or call the configuration-3 runner: it materializes
one train/dev case, stages its source, builds the existing adaptive request
contract, and records immutable identities that an external coordinator can
resume later.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cobol_archaeologist.eval.codex_batch import strict_codex_schema
from cobol_archaeologist.eval.codex_tool import ADAPTIVE_HUNT
from cobol_archaeologist.eval.collaboration_staging import (
    StagedCollaborationTask,
    stage_collaboration_task,
)
from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationGroupIdentity,
    build_collaboration_request,
    ensure_collaboration_request,
)
from cobol_archaeologist.eval.config3_live import (
    CodexAdaptiveEnvelope,
    build_adaptive_codex_prompt,
)
from cobol_archaeologist.eval.materialize import MaterializedSource, materialize
from cobol_archaeologist.schemas import DriftInstance

ROOT = Path(__file__).resolve().parents[3]
MODEL_ID = "gpt-5.6-luna"
REASONING_EFFORT = "max"
TRANSPORT_ID = "collaboration_subagent"
AUTHENTICATION = "in_product_orchestration"
PROMPT_VERSION = "m4-config4-adaptive-dev-v1"
CONFIGURATION = 4
SOURCE_ALIAS = "drift_900000"
MAX_WORKERS = 3
DEFAULT_CASE_LIMIT = 14

DEV_SPLIT_RELATIVE = Path("data/benchmark/v1/dev.jsonl")
TRAIN_SPLIT_RELATIVE = Path("data/benchmark/v1/train.jsonl")
OUTPUT_DIR = ROOT / "data/eval/m4-config4/lineage-v1/train-dev/adaptive_agent"
FREEZE_NAME = "train-dev-freeze-v1.json"
INDEX_NAME = "request-preparation-v1.json"
REQUEST_DIRECTORY_NAME = "requests-v1"
STAGING_DIRECTORY_NAME = "task-staging-v1"
GROUP_ID = "config4:train-dev:adaptive_agent"
_TRIAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

SplitName = Literal["dev", "train", "train-dev"]


def canonical_sha256(value: BaseModel | Mapping[str, Any]) -> str:
    """Hash a model or mapping using the repository's canonical JSON form."""

    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_source_sha256(root: Path = ROOT) -> str:
    """Hash the support runtime without reading benchmark test contents."""

    root = Path(root).resolve()
    paths = [root / "pyproject.toml"]
    paths.extend(sorted((root / "src").rglob("*.py")))
    vendor = root / "vendor" / "tree-sitter-cobol"
    if vendor.is_dir():
        paths.extend(sorted(path for path in vendor.rglob("*") if path.is_file()))
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


class Config4RowPin(BaseModel):
    """A selected train/dev row without gold labels or rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    source_split: Literal["dev", "train"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Config4DevFreeze(BaseModel):
    """Exact, non-headline identity for a provider-free adaptive trial."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-adaptive-dev-freeze-v1"] = (
        "configuration-4-adaptive-dev-freeze-v1"
    )
    configuration: Literal[4] = CONFIGURATION
    status: Literal["TRAIN_DEV_ENGINEERING_ONLY"] = "TRAIN_DEV_ENGINEERING_ONLY"
    headline: Literal[False] = False
    provider: Literal["collaboration_subagent"] = TRANSPORT_ID
    transport: Literal["collaboration_subagent"] = TRANSPORT_ID
    authentication: Literal["in_product_orchestration"] = AUTHENTICATION
    model_id: Literal["gpt-5.6-luna"] = MODEL_ID
    reasoning_effort: Literal["max"] = REASONING_EFFORT
    prompt_version: str = PROMPT_VERSION
    transport_request_schema: Literal[
        "configuration-3-collaboration-request-v2"
    ] = "configuration-3-collaboration-request-v2"
    response_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_split_path: str = DEV_SPLIT_RELATIVE.as_posix()
    dev_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    train_split_path: str = TRAIN_SPLIT_RELATIVE.as_posix()
    train_split_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection: SplitName
    trial_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    max_workers: int = Field(ge=1, le=3)
    authorized_hunts: tuple[Literal["adaptive"], ...] = (ADAPTIVE_HUNT,)
    batch_size: Literal[1] = 1
    one_case_per_task: Literal[True] = True
    max_tool_calls: Literal[16] = 16
    max_steps: Literal[16] = 16
    max_tokens: Literal[98304] = 98304
    hidden_test_rows: Literal[0] = 0
    selected_rows: tuple[Config4RowPin, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _selected_rows_are_development_only(self) -> Config4DevFreeze:
        if any(row.source_split not in {"dev", "train"} for row in self.selected_rows):
            raise ValueError("configuration-4 selection contains a non-development row")
        if len({row.instance_id for row in self.selected_rows}) != len(self.selected_rows):
            raise ValueError("configuration-4 selected rows contain duplicate identities")
        return self


class Config4RequestPin(BaseModel):
    """Request and staged-task identities needed for exact external resume."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=1)
    instance_id: str = Field(pattern=r"^drift_\d{6}$")
    source_split: Literal["dev", "train"]
    run_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_path: str = Field(min_length=1)
    staging_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    staging_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    staging_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_cases: Literal[1] = 1


class Config4DevPreparation(BaseModel):
    """Provider-free readiness receipt; it is not an evaluation result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["configuration-4-adaptive-dev-preparation-v1"] = (
        "configuration-4-adaptive-dev-preparation-v1"
    )
    configuration: Literal[4] = CONFIGURATION
    status: Literal["PROVIDER_FREE_READY_NON_HEADLINE"] = (
        "PROVIDER_FREE_READY_NON_HEADLINE"
    )
    headline: Literal[False] = False
    provider_calls_performed: Literal[0] = 0
    hidden_test_rows: Literal[0] = 0
    one_case_per_task: Literal[True] = True
    freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_count: int = Field(ge=1)
    request_order: tuple[Config4RequestPin, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _request_count_is_exact(self) -> Config4DevPreparation:
        if self.task_count != len(self.request_order):
            raise ValueError("configuration-4 task count differs from request order")
        if [item.ordinal for item in self.request_order] != list(
            range(1, self.task_count + 1)
        ):
            raise ValueError("configuration-4 request ordinals are not contiguous")
        if any(item.visible_cases != 1 for item in self.request_order):
            raise ValueError("configuration-4 adaptive tasks must contain one case")
        return self


def _split_path(root: Path, split: Literal["dev", "train"]) -> Path:
    relative = DEV_SPLIT_RELATIVE if split == "dev" else TRAIN_SPLIT_RELATIVE
    return root / relative


def _load_split(root: Path, split: Literal["dev", "train"]) -> list[DriftInstance]:
    path = _split_path(root, split)
    return [
        DriftInstance.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_train_dev_rows(
    *,
    root: Path = ROOT,
    selection: SplitName = "dev",
    row_ids: Sequence[str] | None = None,
) -> tuple[tuple[DriftInstance, str], ...]:
    """Load only train/dev rows and return each row with its split identity."""

    root = Path(root).resolve()
    split_order: tuple[Literal["dev", "train"], ...] = (
        ("dev",) if selection == "dev" else ("train",) if selection == "train" else ("dev", "train")
    )
    available: dict[str, tuple[DriftInstance, str]] = {}
    for split in split_order:
        for row in _load_split(root, split):
            if row.instance_id in available:
                raise ValueError(f"duplicate train/dev instance identity {row.instance_id}")
            available[row.instance_id] = (row, split)
    if row_ids is None:
        return tuple(available[key] for key in sorted(available))
    requested = tuple(row_ids)
    if len(set(requested)) != len(requested):
        raise ValueError("configuration-4 row_ids contain duplicates")
    missing = [key for key in requested if key not in available]
    if missing:
        raise ValueError(f"requested row is not in the selected train/dev split: {missing[0]}")
    return tuple(available[key] for key in requested)


def _materialize_rows(
    rows: Sequence[tuple[DriftInstance, str]],
    *,
    programs_root: Path | None = None,
    skip_invalid: bool = False,
) -> dict[str, tuple[DriftInstance, str, MaterializedSource]]:
    result: dict[str, tuple[DriftInstance, str, MaterializedSource]] = {}
    for row, split in rows:
        try:
            source = (
                materialize(row)
                if programs_root is None
                else materialize(row, programs_root=Path(programs_root))
            )
        except Exception:
            if skip_invalid:
                continue
            raise
        result[row.instance_id] = (row, split, source)
    return result


def build_config4_dev_freeze(
    *,
    root: Path,
    selection: SplitName,
    trial_id: str,
    rows: Sequence[tuple[DriftInstance, str]],
    materialized: Mapping[str, tuple[DriftInstance, str, MaterializedSource]],
    max_workers: int = MAX_WORKERS,
) -> Config4DevFreeze:
    """Build an immutable method/input identity without writing or calling a provider."""

    root = Path(root).resolve()
    if not _TRIAL_ID_RE.fullmatch(trial_id):
        raise ValueError("configuration-4 trial_id is not path-safe")
    if not rows:
        raise ValueError("configuration-4 development selection is empty")
    if max_workers < 1 or max_workers > 3:
        raise ValueError("configuration-4 max_workers must be between 1 and 3")
    expected_ids = [row.instance_id for row, _ in rows]
    if set(expected_ids) != set(materialized) or len(expected_ids) != len(materialized):
        raise ValueError("materialized configuration-4 rows differ from selection")
    selected = tuple(
        Config4RowPin(
            instance_id=row.instance_id,
            source_split=split,
            source_sha256=materialized[row.instance_id][2].source_sha256,
        )
        for row, split in rows
    )
    schema = strict_codex_schema(CodexAdaptiveEnvelope)
    dev_path = _split_path(root, "dev")
    train_path = _split_path(root, "train")
    return Config4DevFreeze(
        selection=selection,
        trial_id=trial_id,
        max_workers=max_workers,
        response_schema_sha256=canonical_sha256(schema),
        runtime_source_sha256=runtime_source_sha256(root),
        dev_split_sha256=_sha(dev_path),
        train_split_sha256=_sha(train_path),
        selected_rows=selected,
    )


def _run_key(*, freeze: Config4DevFreeze, instance_id: str, source_sha256: str) -> str:
    return canonical_sha256(
        {
            "freeze_sha256": canonical_sha256(freeze),
            "configuration": CONFIGURATION,
            "system_id": "adaptive_agent",
            "run_mode": "train-dev",
            "instance_id": instance_id,
            "source_sha256": source_sha256,
        }
    )


def _write_once(path: Path, payload: bytes) -> None:
    path = Path(path)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"refusing to replace immutable configuration-4 artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _relative_path(root: Path, path: Path) -> str:
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("configuration-4 artifact leaves the repository")
    return resolved.relative_to(root).as_posix()


def _check_unexpected_request_files(request_dir: Path, expected: set[str]) -> None:
    if not request_dir.exists():
        return
    actual = {path.stem for path in request_dir.glob("*.json")}
    if actual - expected:
        raise RuntimeError("configuration-4 request directory contains stale run keys")


def _check_unexpected_staging_dirs(staging_dir: Path, expected: set[str]) -> None:
    if not staging_dir.exists():
        return
    actual = {path.name for path in staging_dir.iterdir() if path.is_dir()}
    if actual - expected:
        raise RuntimeError("configuration-4 staging directory contains stale run keys")


def prepare_config4_adaptive_dev(
    *,
    root: Path = ROOT,
    output_dir: Path = OUTPUT_DIR,
    selection: SplitName = "dev",
    row_ids: Sequence[str] | None = None,
    limit: int | None = DEFAULT_CASE_LIMIT,
    trial_id: str = "trial-01",
    max_workers: int = MAX_WORKERS,
    programs_root: Path | None = None,
) -> Config4DevPreparation:
    """Prepare immutable, one-case adaptive requests without provider calls."""

    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_relative_to(root):
        raise ValueError("configuration-4 output directory leaves the repository")
    if limit is not None and limit < 1:
        raise ValueError("configuration-4 case limit must be positive")
    loaded = list(load_train_dev_rows(root=root, selection=selection, row_ids=row_ids))
    materialized = _materialize_rows(
        loaded,
        programs_root=programs_root,
        skip_invalid=row_ids is None,
    )
    if row_ids is None:
        loaded = [row for row in loaded if row[0].instance_id in materialized]
        loaded = loaded[:limit] if limit is not None else loaded
        materialized = {
            row.instance_id: materialized[row.instance_id]
            for row, _ in loaded
        }
    if not loaded:
        raise ValueError("configuration-4 development selection is empty")
    if {row.instance_id for row, _ in loaded} != set(materialized):
        raise ValueError("configuration-4 materialization differs from selection")
    freeze = build_config4_dev_freeze(
        root=root,
        selection=selection,
        trial_id=trial_id,
        rows=loaded,
        materialized=materialized,
        max_workers=max_workers,
    )
    freeze_path = output_dir / FREEZE_NAME
    _write_once(freeze_path, freeze.model_dump_json(indent=2).encode("utf-8"))
    persisted_freeze = Config4DevFreeze.model_validate_json(
        freeze_path.read_text(encoding="utf-8")
    )
    if persisted_freeze != freeze:
        raise RuntimeError("persisted configuration-4 freeze differs")

    request_dir = output_dir / REQUEST_DIRECTORY_NAME
    staging_dir = output_dir / STAGING_DIRECTORY_NAME
    expected_keys = {
        _run_key(
            freeze=freeze,
            instance_id=row.instance_id,
            source_sha256=materialized[row.instance_id][2].source_sha256,
        )
        for row, _ in loaded
    }
    _check_unexpected_request_files(request_dir, expected_keys)
    _check_unexpected_staging_dirs(staging_dir, expected_keys)
    schema = strict_codex_schema(CodexAdaptiveEnvelope)
    pins: list[Config4RequestPin] = []
    group_mode: Literal["sequential", "concurrent"] = (
        "concurrent" if len(loaded) > 1 else "sequential"
    )
    for ordinal, (row, split) in enumerate(loaded, start=1):
        source = materialized[row.instance_id][2]
        key = _run_key(
            freeze=freeze,
            instance_id=row.instance_id,
            source_sha256=source.source_sha256,
        )
        staged: StagedCollaborationTask = stage_collaboration_task(
            staging_base=staging_dir,
            run_key=key,
            sources={SOURCE_ALIAS: source},
            authorized_hunts=(ADAPTIVE_HUNT,),
        )
        prompt = build_adaptive_codex_prompt(
            alias=SOURCE_ALIAS,
            clause=row.regulation_clause,
            program_scope=Path(row.provenance.base_program).stem,
            tool_command=staged.tool_command,
        )
        request = build_collaboration_request(
            run_key=key,
            prompt=prompt,
            schema=schema,
            sources={SOURCE_ALIAS: source},
            runtime_source_sha256=freeze.runtime_source_sha256,
            authorized_hunts=(ADAPTIVE_HUNT,),
            visible_cases=1,
            group=CollaborationGroupIdentity(
                group_id=GROUP_ID,
                mode=group_mode,
                ordinal=ordinal,
                size=len(loaded),
            ),
        )
        request_path = request_dir / f"{key}.json"
        ensure_collaboration_request(request_path, request)
        expected_request_bytes = request.model_dump_json(indent=2).encode("utf-8")
        if request_path.read_bytes() != expected_request_bytes:
            raise RuntimeError("configuration-4 request artifact bytes are noncanonical")
        manifest_path = staged.task_root / "staging-manifest.json"
        pins.append(
            Config4RequestPin(
                ordinal=ordinal,
                instance_id=row.instance_id,
                source_split=split,
                run_key=key,
                request_sha256=request.request_sha256,
                request_artifact_sha256=_sha(request_path),
                request_path=_relative_path(root, request_path),
                staging_sha256=staged.staging_sha256,
                staging_manifest_sha256=_sha(manifest_path),
                staging_path=_relative_path(root, staged.task_root),
                source_sha256=source.source_sha256,
            )
        )
    preparation = Config4DevPreparation(
        freeze_sha256=canonical_sha256(freeze),
        freeze_artifact_sha256=_sha(freeze_path),
        task_count=len(pins),
        request_order=tuple(pins),
    )
    _write_once(
        output_dir / INDEX_NAME,
        preparation.model_dump_json(indent=2).encode("utf-8"),
    )
    return preparation
