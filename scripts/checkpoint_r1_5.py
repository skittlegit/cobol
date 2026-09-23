"""Replay sealed R1.5 bundles and publish an exact resumable checkpoint."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from cobol_archaeologist.eval.config4_live import canonical_sha256
from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    replay_config4_capture,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/eval/m4/global-smoke-lineage-3"
PREPARATION_PATH = OUTPUT / "full/run-preparation.json"
FIRST_HALF_PATH = OUTPUT / "full/r1.5-first-half.json"
CHECKPOINT_PATH = OUTPUT / "full/r1.5-checkpoint.json"


def _write_checkpoint(payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary = CHECKPOINT_PATH.with_suffix(".json.tmp")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    temporary.replace(CHECKPOINT_PATH)


def main() -> None:
    preparation = Config4RunPreparation.model_validate_json(
        PREPARATION_PATH.read_text(encoding="utf-8")
    )
    first_half = json.loads(FIRST_HALF_PATH.read_text(encoding="utf-8"))
    selected = first_half["task_keys"]
    tasks = {task.task_key: task for task in preparation.tasks}
    if set(selected) - tasks.keys():
        raise RuntimeError("R1.5 selection contains an unknown prepared task")

    sealed: list[str] = []
    execution_sha256: dict[str, str] = {}
    sealed_by_system: Counter[str] = Counter()
    for task_key in selected:
        task = tasks[task_key]
        complete = task.artifact_dir / "raw" / task_key / "complete"
        if not complete.is_file():
            continue
        execution = replay_config4_capture(task=task)
        sealed.append(task_key)
        sealed_by_system[task.system_id] += 1
        execution_sha256[task_key] = canonical_sha256(execution)

    required_by_system = first_half["system_task_counts"]
    checkpoint = {
        "schema_version": "configuration-4-r1.5-checkpoint-v1",
        "full_run_identity_sha256": first_half["full_run_identity_sha256"],
        "first_half_order_sha256": first_half["task_order_sha256"],
        "required_tasks": len(selected),
        "sealed_tasks": len(sealed),
        "remaining_tasks": len(selected) - len(sealed),
        "sealed_by_system": {
            system: sealed_by_system[system] for system in required_by_system
        },
        "remaining_by_system": {
            system: required - sealed_by_system[system]
            for system, required in required_by_system.items()
        },
        "sealed_task_keys": sealed,
        "sealed_task_order_sha256": canonical_sha256(sealed),
        "execution_sha256": execution_sha256,
        "status": "COMPLETE" if len(sealed) == len(selected) else "IN_PROGRESS",
    }
    _write_checkpoint(checkpoint)
    print(json.dumps(checkpoint, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
