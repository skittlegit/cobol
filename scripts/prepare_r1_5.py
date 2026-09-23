"""Authorize and prepare the immutable R1.5 one-time hidden run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cobol_archaeologist.eval.config3_live import _load_split
from cobol_archaeologist.eval.config4_live import (
    canonical_sha256,
    load_config4_frozen_identity,
    require_config4_full_smoke_readiness,
)
from cobol_archaeologist.eval.config4_runner import (
    Config4RunPreparation,
    prepare_config4_run,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/eval/m4/global-smoke-lineage-3"


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_immutable(path: Path, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"refusing to replace immutable {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output
    freeze_path = output / "run-freeze.json"
    readiness_path = output / "smoke-readiness.json"
    identity_path = output / "full-run-identity.json"
    first_half_path = output / "full/r1.5-first-half.json"
    freeze = load_config4_frozen_identity(freeze_path)
    preparation_path = output / "full/run-preparation.json"
    if identity_path.exists():
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        preparation = Config4RunPreparation.model_validate_json(
            preparation_path.read_text(encoding="utf-8")
        )
        if identity["freeze_sha256"] != canonical_sha256(freeze):
            raise RuntimeError("immutable full-run freeze identity differs")
        if identity["preparation_sha256"] != canonical_sha256(preparation):
            raise RuntimeError("immutable full-run preparation identity differs")
        if identity["smoke_readiness_sha256"] != _sha_file(readiness_path):
            raise RuntimeError("immutable full-run readiness artifact differs")
    else:
        # This gate is deliberately evaluated before opening the held-out split.
        readiness = require_config4_full_smoke_readiness(
            output_dir=output, freeze=freeze
        )
        readiness_sha256 = _sha_file(readiness_path)

        test_path = ROOT / freeze.test_split_path
        if _sha_file(test_path) != freeze.test_split_sha256:
            raise RuntimeError("configuration-4 hidden split hash differs")
        rows = _load_split(test_path)
        if tuple(row.instance_id for row in rows) != freeze.test_order:
            raise RuntimeError("configuration-4 hidden roster order differs")

        preparation = prepare_config4_run(
            freeze=freeze,
            rows=rows,
            mode="full",
            output_dir=output,
            root=ROOT,
        )
        task_order = [task.task_key for task in preparation.tasks]
        identity = {
            "schema_version": "configuration-4-full-run-identity-v1",
            "configuration": 4,
            "run_mode": "full",
            "freeze_sha256": canonical_sha256(freeze),
            "smoke_readiness_sha256": readiness_sha256,
            "smoke_readiness_identity_sha256": canonical_sha256(readiness),
            "test_split_sha256": freeze.test_split_sha256,
            "hidden_test_roster_sha256": freeze.hidden_test_roster_sha256,
            "row_count": len(rows),
            "row_order_sha256": canonical_sha256(list(freeze.test_order)),
            "task_count": preparation.task_count,
            "task_order": task_order,
            "task_order_sha256": canonical_sha256(task_order),
            "preparation_sha256": canonical_sha256(preparation),
            "provider_calls_performed": 0,
            "hidden_labels_exposed_to_requests": False,
        }
        _write_immutable(identity_path, identity)

    midpoint = len(preparation.row_order) // 2
    row_positions = {
        instance_id: index for index, instance_id in enumerate(freeze.test_order)
    }
    selected_by_system: dict[str, list[str]] = {
        system: [] for system in preparation.systems
    }
    for task in preparation.tasks:
        row_indexes = [row_positions[value] for value in task.row_instance_ids]
        if min(row_indexes) < midpoint:
            selected_by_system[task.system_id].append(task.task_key)
    first_half_tasks = [
        task_key
        for ordinal in range(max(map(len, selected_by_system.values())))
        for system in preparation.systems
        for task_key in selected_by_system[system][ordinal : ordinal + 1]
    ]
    first_half = {
        "schema_version": "configuration-4-r1.5-first-half-v1",
        "full_run_identity_sha256": canonical_sha256(identity),
        "row_midpoint": midpoint,
        "selection_rule": (
            "for each frozen system task order, include every immutable task whose "
            "first row index is below floor(test_rows/2); batched controls may cross "
            "the midpoint; interleave selected tasks by ordinal then frozen system "
            "order"
        ),
        "task_count": len(first_half_tasks),
        "system_task_counts": {
            system: len(task_keys)
            for system, task_keys in selected_by_system.items()
        },
        "task_keys": first_half_tasks,
        "task_order_sha256": canonical_sha256(first_half_tasks),
    }
    _write_immutable(first_half_path, first_half)
    print(
        json.dumps(
            {
                "full_run_identity_sha256": canonical_sha256(identity),
                "preparation_sha256": canonical_sha256(preparation),
                "rows": len(preparation.row_order),
                "tasks": preparation.task_count,
                "r1_5_tasks": len(first_half_tasks),
                "provider_calls_performed": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
