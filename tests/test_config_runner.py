"""Provider-free request, staging, sealing, and gate tests for configuration 4."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cobol_archaeologist.eval.baselines import PlainLLMContext
from cobol_archaeologist.eval.config3_live import Config3RunFreeze
from cobol_archaeologist.eval.config4_live import (
    CONFIG4_SYSTEMS,
    build_config4_freeze,
    canonical_sha256,
    config4_run_key,
    refresh_config4_smoke_readiness,
)
from cobol_archaeologist.eval.config4_runner import (
    load_config4_smoke_rows,
    prepare_config4_run,
    replay_config4_capture,
    seal_config4_capture,
    update_config4_progress,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG3_FREEZE_PATH = (
    ROOT / "data/eval/legacy/m4-config3/lineage-v4/run-freeze-v2.json"
)


def _freeze(tmp_path: Path):
    predecessor = Config3RunFreeze.model_validate_json(
        CONFIG3_FREEZE_PATH.read_text(encoding="utf-8")
    )
    return build_config4_freeze(
        predecessor=predecessor,
        prompt="The frozen configuration-4 adaptive prompt.",
        response_schema={"type": "object", "additionalProperties": False},
        tool_policy="one bounded command",
        verifier_identity="config3-verifier-preserved",
        runner_identity="config4-runner-v1",
        output_root=tmp_path / "m4",
    )


def _context_builder(system_id, *, rows, sources, regulation_search=None):
    return {
        row.instance_id: PlainLLMContext(
            clause=row.regulation_clause,
            program="bounded-program-context",
        )
        for row in rows
    }


def _prepare(tmp_path: Path):
    freeze = _freeze(tmp_path)
    rows = load_config4_smoke_rows(freeze, root=ROOT)
    preparation = prepare_config4_run(
        freeze=freeze,
        rows=rows,
        mode="smoke",
        output_dir=tmp_path / "m4",
        root=ROOT,
        context_builder=_context_builder,
    )
    return freeze, rows, preparation


def test_smoke_preparation_seals_exact_all_six_roster_without_provider(
    tmp_path: Path,
):
    freeze, rows, preparation = _prepare(tmp_path)

    assert preparation.provider_calls_performed == 0
    assert preparation.row_order == tuple(row.instance_id for row in rows)
    assert preparation.task_count == 37
    assert preparation.systems == CONFIG4_SYSTEMS
    counts = {
        system_id: sum(task.system_id == system_id for task in preparation.tasks)
        for system_id in CONFIG4_SYSTEMS
    }
    assert counts == {
        "agent": 7,
        "adaptive_agent": 14,
        "plain_llm": 3,
        "rag_dense": 3,
        "rag_reranker": 3,
        "oracle_slice": 7,
    }
    adaptive = [
        task for task in preparation.tasks if task.system_id == "adaptive_agent"
    ]
    assert all(len(task.row_instance_ids) == 1 for task in adaptive)
    assert all(task.staging_sha256 for task in adaptive)
    assert all(task.request_path.is_file() for task in preparation.tasks)
    assert all(
        task.request_path.parent.name == "requests" for task in preparation.tasks
    )
    assert (tmp_path / "m4/smoke/adaptive_agent/task-staging").is_dir()
    assert (tmp_path / "m4/smoke/plain_llm/task-staging").exists() is False
    assert canonical_sha256(freeze) == preparation.freeze_sha256


def test_full_preparation_checks_smoke_before_touching_rows(tmp_path: Path):
    freeze = _freeze(tmp_path)

    with pytest.raises(RuntimeError, match="no completed configuration-4 smoke"):
        prepare_config4_run(
            freeze=freeze,
            rows=[],
            mode="full",
            output_dir=tmp_path / "m4",
            root=ROOT,
            context_builder=_context_builder,
        )

    assert not (tmp_path / "m4-config4/full").exists()


def test_full_preparation_reaches_frozen_row_check_only_after_smoke_gate(
    tmp_path: Path,
):
    freeze = _freeze(tmp_path)
    output = tmp_path / "m4"
    for system_id in CONFIG4_SYSTEMS:
        keys = [
            config4_run_key(
                freeze=freeze,
                system_id=system_id,
                run_mode="smoke",
                instance_id=instance_id,
                source_sha256=freeze.source_sha256[instance_id],
            )
            for instance_id in freeze.smoke_instance_ids
        ]
        update_config4_progress(
            freeze=freeze,
            output_dir=output,
            mode="smoke",
            system_id=system_id,
            completed_run_keys=keys,
            pending_instance_ids=[],
            interruptions={},
        )
    assert refresh_config4_smoke_readiness(output_dir=output, freeze=freeze)

    with pytest.raises(ValueError, match="full rows differ"):
        prepare_config4_run(
            freeze=freeze,
            rows=[],
            mode="full",
            output_dir=output,
            root=ROOT,
            context_builder=_context_builder,
        )
    assert not (output / "full").exists()


def test_baseline_capture_seals_and_replays_from_prepared_identity(tmp_path: Path):
    _, _, preparation = _prepare(tmp_path)
    task = next(task for task in preparation.tasks if task.system_id == "plain_llm")
    final_json = json.dumps(
        {
            "results": [
                {
                    "alias": "drift_900000",
                    "clause_index": None,
                    "response": {
                        "kind": "abstain",
                        "thought": "No finding is supported.",
                        "prediction": None,
                        "claim": None,
                        "exec_probe": None,
                        "static_claim": None,
                        "abstention_reason": "qualification fixture",
                        "final_answer": "Abstained: qualification fixture",
                    },
                }
            ]
        },
        separators=(",", ":"),
    )
    execution = seal_config4_capture(
        task=task,
        final_json=final_json,
        task_name="/root/config4/plain_llm_01",
        task_id="config4-task-plain-01",
    )
    replay = replay_config4_capture(task=task)

    assert execution == replay
    assert execution.final_message == final_json
    assert execution.request.run_key == task.task_key
    assert hashlib.sha256(final_json.encode()).hexdigest() == (
        execution.parsed.events[-1]["payload"]["final_sha256"]
    )
