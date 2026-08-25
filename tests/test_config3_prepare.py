"""Provider-free gates for the configuration-3 smoke preparation CLI."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cobol_archaeologist.eval.collaboration_transport import (
    CollaborationGroupIdentity,
    build_collaboration_request,
    ensure_collaboration_request,
)
from cobol_archaeologist.eval.config3_live import (
    CONFIG3_SYSTEMS,
    Config3RunFreeze,
    ensure_frozen_identity,
)
from cobol_archaeologist.eval.config3_prepare import (
    INDEX_NAME,
    CollaborationSmokePlan,
    build_collaboration_smoke_freeze,
    write_smoke_request_preparation,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/eval/m4-config3/collaboration-smoke-plan-v2.json"
DEVELOPMENT = ROOT / "data/eval/m4-config3/development-smoke.json"


def _freeze(plan: CollaborationSmokePlan) -> Config3RunFreeze:
    return Config3RunFreeze(
        provider="collaboration_subagent",
        authentication="in_product_orchestration",
        prompt_version="m4-config3-adaptive-v1",
        repository_commit="a" * 40,
        runtime_source_sha256="b" * 64,
        transport="collaboration_subagent",
        max_workers=plan.max_concurrent_tasks,
        systems=CONFIG3_SYSTEMS,
        budgets={},
        batch_sizes={item.system_id: item.batch_size for item in plan.systems},
        identity_hashes={},
        phase5_baseline_sha256={},
        phase5_aggregate_sha256={},
        dev_split_path="data/benchmark/v1/dev.jsonl",
        dev_split_sha256="c" * 64,
        train_split_path="data/benchmark/v1/train.jsonl",
        train_split_sha256="d" * 64,
        test_split_path="data/benchmark/v1/test.jsonl",
        test_split_sha256="e" * 64,
        t6_v2_path="data/benchmark/t6-v2/final/manifest.json",
        t6_v2_sha256="f" * 64,
        smoke_seed=20_260_824,
        smoke_instance_ids=tuple(f"drift_{index:06d}" for index in range(14)),
        dev_order=(),
        test_order=(),
        t6_order=(),
        t6_source_inputs={},
        source_sha256={},
    )


def _request_key(system_id: str, ordinal: int) -> str:
    return hashlib.sha256(f"{system_id}:{ordinal}".encode()).hexdigest()


def _write_requests(
    *, output_dir: Path, plan: CollaborationSmokePlan, skip_last: bool
) -> None:
    for system_index, item in enumerate(plan.systems):
        remaining = plan.row_count
        for ordinal in range(1, item.task_count + 1):
            if (
                skip_last
                and system_index == len(plan.systems) - 1
                and ordinal == item.task_count
            ):
                continue
            visible = min(item.batch_size, remaining)
            remaining -= visible
            run_key = _request_key(item.system_id, ordinal)
            request = build_collaboration_request(
                run_key=run_key,
                prompt=f"frozen {item.system_id} smoke task {ordinal}",
                schema={"type": "object", "additionalProperties": False},
                sources={},
                runtime_source_sha256="b" * 64,
                authorized_hunts=(),
                visible_cases=visible,
                group=CollaborationGroupIdentity(
                    group_id=item.group_id,
                    mode=item.group_mode,
                    ordinal=ordinal,
                    size=item.task_count,
                ),
            )
            ensure_collaboration_request(
                output_dir
                / "smoke"
                / item.system_id
                / Path(item.request_artifact_directory).name
                / f"{run_key}.json",
                request,
            )


def test_freeze_dependency_refusal_writes_nothing(tmp_path: Path, monkeypatch):
    plan_path = tmp_path / "data/eval/m4-config3/collaboration-smoke-plan-v2.json"
    development_path = tmp_path / "data/eval/m4-config3/development-smoke.json"
    manifest_path = tmp_path / "data/benchmark/t6-v2/final/manifest.json"
    plan_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True)
    plan_path.write_bytes(PLAN.read_bytes())
    development_path.write_bytes(DEVELOPMENT.read_bytes())
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "cobol_archaeologist.eval.config3_prepare.repository_commit",
        lambda _root: "a" * 40,
    )

    with pytest.raises(RuntimeError, match="no valid finalized 40-side"):
        build_collaboration_smoke_freeze(root=tmp_path)

    assert not (
        tmp_path / "data/eval/m4-config3/lineage-v4/run-freeze-v2.json"
    ).exists()
    assert not list(tmp_path.rglob("requests"))


def test_readiness_transitions_only_after_all_37_typed_requests(tmp_path: Path):
    plan = CollaborationSmokePlan.model_validate_json(PLAN.read_text(encoding="utf-8"))
    freeze = _freeze(plan)
    output = tmp_path / "data/eval/m4-config3/lineage-v4"
    ensure_frozen_identity(output / "run-freeze-v2.json", freeze)
    _write_requests(output_dir=output, plan=plan, skip_last=True)

    with pytest.raises(RuntimeError, match="typed request roster is incomplete"):
        write_smoke_request_preparation(
            freeze=freeze,
            plan=plan,
            plan_path=PLAN,
            output_dir=output,
            root=tmp_path,
        )
    assert not (output / INDEX_NAME).exists()

    _write_requests(output_dir=output, plan=plan, skip_last=False)
    preparation = write_smoke_request_preparation(
        freeze=freeze,
        plan=plan,
        plan_path=PLAN,
        output_dir=output,
        root=tmp_path,
    )

    assert preparation.status == "MODEL_PROMPTS_READY_TRANSCRIPT_PROTOCOL_PENDING"
    assert preparation.provider_calls_performed == 0
    assert preparation.task_count == 37
    assert sum(item.visible_cases for item in preparation.request_order) == 84
    assert len({item.run_key for item in preparation.request_order}) == 37
    assert (output / INDEX_NAME).is_file()
    assert not (output / "smoke-request-preparation.json").exists()
