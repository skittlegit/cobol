"""Replay sealed R1.5 work and list only immutable unsealed tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    replay_config4_capture,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/eval/m4/global-smoke-lineage-3"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument(
        "--prefer-system",
        action="append",
        default=[],
        help=(
            "Schedule these systems first, in the supplied order, while "
            "preserving immutable order within each system."
        ),
    )
    args = parser.parse_args()
    preparation = Config4RunPreparation.model_validate_json(
        (OUTPUT / "full/run-preparation.json").read_text(encoding="utf-8")
    )
    first_half = json.loads(
        (OUTPUT / "full/r1.5-first-half.json").read_text(encoding="utf-8")
    )
    tasks = {task.task_key: task for task in preparation.tasks}
    pending = []
    sealed = 0
    for task_key in first_half["task_keys"]:
        task = tasks[task_key]
        complete = task.artifact_dir / "raw" / task_key / "complete"
        if complete.is_file():
            replay_config4_capture(task=task)
            sealed += 1
        elif task_key not in args.exclude:
            pending.append(
                {
                    "system_id": task.system_id,
                    "ordinal": task.ordinal,
                    "task_key": task.task_key,
                    "request_path": str(task.request_path),
                    "artifact_dir": str(task.artifact_dir),
                    "staging_base": (
                        str(task.staging_base) if task.staging_base else None
                    ),
                    "capture_path": str(
                        OUTPUT
                        / "full-captured-finals"
                        / f"{task.system_id}-{task.ordinal:03d}.json"
                    ),
                }
            )
    if args.prefer_system:
        priority = {
            system_id: index
            for index, system_id in enumerate(args.prefer_system)
        }
        pending.sort(
            key=lambda task: priority.get(task["system_id"], len(priority))
        )
    print(
        json.dumps(
            {
                "required": len(first_half["task_keys"]),
                "sealed_and_replayed": sealed,
                "remaining": len(first_half["task_keys"]) - sealed,
                "next_unsealed": pending[: args.limit],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
