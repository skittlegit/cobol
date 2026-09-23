"""Replay sealed R1.5 bundles and publish an exact resumable checkpoint."""

from __future__ import annotations

import argparse
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
def _write_checkpoint(path: Path, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output
    preparation = Config4RunPreparation.model_validate_json(
        (output / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    first_half = json.loads((output / "full/r1.5-first-half.json").read_text(encoding="utf-8"))
    selected = first_half["task_keys"]
    terminal_path = output / "full/terminal-attempts.json"
    terminal_keys: set[str] = set()
    if terminal_path.exists():
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        if terminal["full_run_identity_sha256"] != first_half["full_run_identity_sha256"]:
            raise RuntimeError("terminal attempts differ from frozen full-run identity")
        terminal_keys = {attempt["task_key"] for attempt in terminal["attempts"]}
        if terminal_keys - set(selected):
            raise RuntimeError("terminal attempts contain an unknown first-half key")
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
    if terminal_keys.intersection(sealed):
        raise RuntimeError("terminal attempt is also sealed")
    checkpoint = {
        "schema_version": "configuration-4-r1.5-checkpoint-v1",
        "full_run_identity_sha256": first_half["full_run_identity_sha256"],
        "first_half_order_sha256": first_half["task_order_sha256"],
        "required_tasks": len(selected),
        "sealed_tasks": len(sealed),
        "remaining_tasks": len(selected) - len(sealed),
        "terminal_contract_rejections": len(terminal_keys),
        "terminal_task_keys": sorted(terminal_keys),
        "pending_runnable_tasks": len(selected) - len(sealed) - len(terminal_keys),
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
    _write_checkpoint(output / "full/r1.5-checkpoint.json", checkpoint)
    print(json.dumps(checkpoint, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
