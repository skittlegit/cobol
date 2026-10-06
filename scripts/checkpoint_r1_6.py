"""Replay the immutable full-run roster and checkpoint R1.6 without provider calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from cobol_archaeologist.eval.config4_live import (
    canonical_sha256,
    load_config4_frozen_identity,
)
from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    _task_request,
    replay_config4_capture,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    output = args.output.resolve()
    handoff_path = output / "full/r1.5-handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if handoff["status"] != "COMPLETE" or handoff["first_half_pending_tasks"]:
        raise RuntimeError("R1.6 requires the terminal R1.5 handoff")
    for name, expected in handoff["evidence_sha256"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"R1.5 handoff evidence changed: {name}")
    preparation = Config4RunPreparation.model_validate_json(
        (output / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    identity = json.loads(
        (output / "full-run-identity.json").read_text(encoding="utf-8")
    )
    freeze = load_config4_frozen_identity(output / "run-freeze.json")
    if (
        canonical_sha256(identity) != handoff["full_run_identity_sha256"]
        or canonical_sha256(preparation) != identity["preparation_sha256"]
        or canonical_sha256(freeze) != identity["freeze_sha256"]
        or [task.task_key for task in preparation.tasks] != identity["task_order"]
    ):
        raise RuntimeError("full-run identity, freeze, preparation, or order changed")
    selected = set(handoff["full_run_pending_task_keys"])
    if len(selected) != handoff["full_run_pending_tasks"]:
        raise RuntimeError("R1.6 initial pending roster has duplicate keys")
    all_keys = {task.task_key for task in preparation.tasks}
    if selected - all_keys:
        raise RuntimeError("R1.6 roster contains an unknown task")
    sealed: list[str] = []
    pending = []
    sealed_by_system: Counter[str] = Counter()
    required_by_system: Counter[str] = Counter()
    execution_sha256 = {}
    for task in preparation.tasks:
        required_by_system[task.system_id] += 1
        if (task.artifact_dir / "raw" / task.task_key / "complete").is_file():
            execution = replay_config4_capture(task=task)
            sealed.append(task.task_key)
            sealed_by_system[task.system_id] += 1
            execution_sha256[task.task_key] = canonical_sha256(execution)
        else:
            if task.task_key not in selected:
                raise RuntimeError("a previously sealed handoff key is now missing")
            _task_request(task)
            pending.append(
                {
                    "system_id": task.system_id,
                    "ordinal": task.ordinal,
                    "task_key": task.task_key,
                    "request_path": str(task.request_path),
                }
            )
    checkpoint = {
        "schema_version": "configuration-4-r1.6-checkpoint-v1",
        "full_run_identity_sha256": handoff["full_run_identity_sha256"],
        "r1_5_handoff_sha256": hashlib.sha256(handoff_path.read_bytes()).hexdigest(),
        "required_full_run_tasks": len(preparation.tasks),
        "initial_sealed_full_run_tasks": handoff["full_run_sealed_and_replayed_tasks"],
        "r1_6_required_tasks": len(selected),
        "r1_6_sealed_tasks": len(selected.intersection(sealed)),
        "sealed_full_run_tasks": len(sealed),
        "pending_full_run_tasks": len(pending),
        "sealed_by_system": dict(sealed_by_system),
        "pending_by_system": {
            system: required - sealed_by_system[system]
            for system, required in required_by_system.items()
        },
        "sealed_task_keys": sealed,
        "execution_sha256": execution_sha256,
        "pending_tasks": pending,
        "temporal_status": "PENDING",
        "status": "FULL_RUN_COMPLETE_TEMPORAL_PENDING"
        if not pending
        else "IN_PROGRESS",
    }
    path = output / "full/r1.6-checkpoint.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(checkpoint, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)
    print(
        json.dumps(
            {
                "sealed_full_run_tasks": len(sealed),
                "r1_6_sealed_tasks": checkpoint["r1_6_sealed_tasks"],
                "pending_full_run_tasks": len(pending),
                "pending_by_system": checkpoint["pending_by_system"],
                "status": checkpoint["status"],
                "next_unsealed": [
                    task for task in pending if task["task_key"] not in args.exclude
                ][: args.limit],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
